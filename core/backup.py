"""
Backup and restore for Nexora SafarPro.

A backup is a single .zip file in %LOCALAPPDATA%\\Nexora\\SafarPro\\backups\\ containing:
    safarpro.sqlite3   consistent snapshot made with SQLite's online-backup API
    documents/...      every uploaded document
    manifest.json      app version, time, SHA-256 of the database, record counts

Restore (only while the server is stopped):
    1. validates the zip (manifest, checksum, SQLite integrity check, required tables),
    2. takes a safety backup of the CURRENT data first,
    3. swaps the database atomically and restores documents,
    4. keeps the previous documents folder renamed, never deleted.
"""
import datetime as dt
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings

REQUIRED_TABLES = {"django_migrations", "auth_user", "core_organization", "operations_booking", "finance_payment", "finance_journalentry"}
COUNT_TABLES = {"customers": "crm_customer", "bookings": "operations_booking", "payments": "finance_payment", "journal_entries": "finance_journalentry",
                "documents": "crm_document", "employees": "accounts_employee"}


class BackupError(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _counts(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        out = {}
        for k, t in COUNT_TABLES.items():
            try:
                out[k] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                out[k] = None
        return out
    finally:
        con.close()


def snapshot_database(dest):
    """Consistent copy of the live database, safe while the app is running."""
    src = sqlite3.connect(str(settings.DB_PATH), timeout=30)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def create_backup(label="manual"):
    if not Path(settings.DB_PATH).exists():
        raise BackupError("There is no database to back up yet.")
    settings.BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"SafarPro-backup-{stamp}-{label}.zip"
    final = settings.BACKUP_ROOT / name
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "safarpro.sqlite3"
        snapshot_database(snap)
        docs = [p for p in settings.DOCUMENTS_ROOT.rglob("*") if p.is_file() and not p.name.endswith(".part")]
        manifest = {"app": settings.APP_NAME, "version": settings.APP_VERSION, "created": dt.datetime.now().isoformat(timespec="seconds"),
                    "label": label, "db_sha256": _sha256(snap), "counts": _counts(snap), "documents": len(docs)}
        tmp = final.with_suffix(".zip.part")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "safarpro.sqlite3")
            for p in docs:
                z.write(p, "documents/" + p.relative_to(settings.DOCUMENTS_ROOT).as_posix())
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
        os.replace(tmp, final)
    validate_backup(final)  # never report success for a backup that cannot be restored
    return final, manifest


def list_backups():
    out = []
    for p in sorted(settings.BACKUP_ROOT.glob("SafarPro-backup-*.zip"), reverse=True):
        st = p.stat()
        out.append({"name": p.name, "size": st.st_size, "at": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%dT%H:%M")})
    return out


def validate_backup(path):
    path = Path(path)
    if not path.exists():
        raise BackupError(f"Backup file not found: {path}")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise BackupError("This file is not a valid SafarPro backup (not a zip archive).")
    with z:
        names = set(z.namelist())
        if "manifest.json" not in names or "safarpro.sqlite3" not in names:
            raise BackupError("This file is not a SafarPro backup (manifest or database missing).")
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts or ":" in n:
                raise BackupError("Backup contains unsafe file paths and was rejected.")
        if z.testzip() is not None:
            raise BackupError("Backup archive is damaged (checksum error).")
        manifest = json.loads(z.read("manifest.json"))
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "check.sqlite3"
            with z.open("safarpro.sqlite3") as s, open(db, "wb") as d:
                shutil.copyfileobj(s, d)
            if manifest.get("db_sha256") and _sha256(db) != manifest["db_sha256"]:
                raise BackupError("Database checksum does not match the manifest — the backup is corrupted.")
            con = sqlite3.connect(str(db))
            try:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("The database inside the backup failed SQLite's integrity check.")
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.DatabaseError as e:
                raise BackupError(f"The database inside the backup is not readable ({e}).")
            finally:
                con.close()
            missing = REQUIRED_TABLES - tables
            if missing:
                raise BackupError("Backup database is missing SafarPro tables: " + ", ".join(sorted(missing)))
    return manifest


def server_running(host=None, port=None):
    host, port = host or settings.SERVER_HOST, port or settings.SERVER_PORT
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def restore_backup(path, *, force_running=False):
    path = Path(path)
    manifest = validate_backup(path)
    if server_running() and not force_running:
        raise BackupError("SafarPro is still running. Close the SafarPro server window first, then restore.")
    from django.db import connections
    connections.close_all()
    safety = None
    if Path(settings.DB_PATH).exists():
        safety, _ = create_backup(label="before-restore")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    with zipfile.ZipFile(path) as z:
        tmp_db = settings.DB_DIR / f"restore-{stamp}.sqlite3.part"
        with z.open("safarpro.sqlite3") as s, open(tmp_db, "wb") as d:
            shutil.copyfileobj(s, d)
            d.flush()
            os.fsync(d.fileno())
        for suffix in ("-wal", "-shm"):
            side = Path(str(settings.DB_PATH) + suffix)
            if side.exists():
                side.unlink()
        os.replace(tmp_db, settings.DB_PATH)
        # Keep the current documents folder (renamed), then extract the backup's documents.
        if settings.DOCUMENTS_ROOT.exists() and any(settings.DOCUMENTS_ROOT.iterdir()):
            settings.DOCUMENTS_ROOT.rename(settings.DATA_ROOT / f"documents-before-restore-{stamp}")
        settings.DOCUMENTS_ROOT.mkdir(parents=True, exist_ok=True)
        root = settings.DOCUMENTS_ROOT.resolve()
        for n in z.namelist():
            if n.startswith("documents/") and not n.endswith("/"):
                target = (settings.DOCUMENTS_ROOT / n[len("documents/"):]).resolve()
                if root not in target.parents:
                    raise BackupError("Unsafe path in backup.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as s, open(target, "wb") as d:
                    shutil.copyfileobj(s, d)
    return manifest, safety
