# Nexora SafarPro

**Offline travel agency management for Windows — by Nexora.**

SafarPro runs entirely on your own PC. A small local server (Django + SQLite) starts on
`127.0.0.1`, and you use the app in your normal web browser. Nothing is sent to the
internet, and other computers on your network cannot reach it.

---

## 1. What you need

| Item | Notes |
|---|---|
| Windows 10 or 11 | 64-bit |
| Python 3.10 or newer | Free from <https://www.python.org/downloads/windows/> |
| Internet **once** during setup | To download Django and waitress (about 12 MB). After setup SafarPro works fully offline. |
| A modern browser | Edge, Chrome or Firefox |

---

## 2. Install (one time)

1. **Install Python.**
   Download the Windows installer from python.org and run it.
   On the first screen, tick **"Add python.exe to PATH"**, then click **Install Now**.
2. **Put the SafarPro folder somewhere permanent**, for example
   `C:\Users\<you>\Documents\Nexora-SafarPro`.
   (Don't run it from inside a zip file — extract it first.)
3. **Double-click `setup_windows.bat`.**
   It will:
   - check your Python version,
   - create a private program environment in the `.venv` folder,
   - install Django and waitress,
   - prepare the database (if data already exists, it is backed up first),
   - create a **Nexora SafarPro** shortcut on your desktop.

   Wait until it says **"Setup complete"**, then press a key to close it.

> If Windows shows "Windows protected your PC", click **More info → Run anyway**.
> The .bat files are plain text; you can open them in Notepad to see exactly what they do.

---

## 3. Start SafarPro

1. Double-click **`run_safarpro.bat`** (or the desktop shortcut).
2. A black window titled *"Nexora SafarPro - Server"* opens. **Keep it open** while you work.
3. Your browser opens at <http://127.0.0.1:8765/> (bookmark it).

### First start only: create your agency

The browser shows a **Set up your agency** page:

- agency name, city, main branch name and code,
- the administrator's name, username and password (at least 8 characters, not a common password).

There is **no built-in default password** — the account you create here is the only way in.
Write the password down somewhere safe.

Tick **"Add fictional sample records"** only if you want to try the app with demo data.
For real business use, leave it unticked.

### Daily use

- Sign in with your username and password.
- Add staff logins under **Employees → Create login**, and choose each person's role.
  Roles are enforced by the server: a Receptionist, for example, cannot record payments
  or see accounting reports, even by calling the server directly.
- The top bar shows **"Local · saved"** when the server is reachable. If it shows
  **"Server stopped"**, start `run_safarpro.bat` again — nothing you saved is lost.

### Stop SafarPro

Close the black server window (or press **Ctrl + C** in it). Every change is saved to the
database the moment it is made, so there is no "save" step.

---

## 4. Where your data is kept

Everything lives outside the program folder, so updating or reinstalling the program never
touches it:

```
%LOCALAPPDATA%\Nexora\SafarPro\
    data\safarpro.sqlite3     the database (customers, bookings, accounts, ...)
    data\secret_key.txt       session signing key, created once
    documents\                uploaded passports, CNICs, tickets, visas
    backups\                  backup .zip files
    logs\                     error log (safarpro.log)
```

Type `%LOCALAPPDATA%\Nexora\SafarPro` into the File Explorer address bar to open it.
The **Data & Backups** page in the app also shows these locations, file sizes and a ledger health check.

**SafarPro never deletes or resets this folder** — not on first start, not on upgrade, not on reinstall.

---

## 5. Backups

**Make one at the end of every working day, and copy it off the PC** (USB drive, Google Drive, OneDrive).
A backup that only lives on the same hard disk doesn't protect you from disk failure or theft.

Two ways to back up (both are safe while SafarPro is running):

- In the app: **Data & Backups → Back up now**, then **Download**.
- Double-click **`backup_safarpro.bat`**; it opens the backups folder when it's done.

Each backup is one `.zip` file containing a consistent copy of the database, every uploaded
document, and a manifest with a SHA-256 checksum. A backup is checked (checksum + SQLite integrity
check) right after it's written, so you are never told a backup succeeded when it can't be restored.

## 6. Restore a backup

1. **Close the SafarPro server window.** Restore refuses to run while the server is running.
2. Double-click **`restore_safarpro.bat`**.
3. Drag the backup `.zip` file into the window (or type its name) and press Enter.
4. The file is validated first. If it's damaged or not a SafarPro backup, nothing is changed.
5. Type `RESTORE` to confirm.
6. SafarPro **automatically backs up your current data first**
   (`SafarPro-backup-...-before-restore.zip`). The old documents folder is renamed and kept,
   not deleted. So a restore can always be undone.
7. Start SafarPro again with `run_safarpro.bat`.

---

## 7. Moving to a new PC

1. On the old PC: make a backup and copy the `.zip` to a USB drive.
2. On the new PC: install Python, copy the SafarPro folder, run `setup_windows.bat`.
3. Run `restore_safarpro.bat` and choose the backup. **Don't** complete the first-run setup page first —
   restore straight away. (If you already did, it doesn't matter: the restore replaces it, after a safety backup.)

## 8. Updating SafarPro

1. Make a backup.
2. Replace the program files with the new version (keep the `.venv` folder, or just run setup again).
3. Run `setup_windows.bat`. If the update changes the database structure, a backup labelled
   `before-update` is created automatically before anything changes.

## 9. Starting fresh

Because SafarPro never deletes data on its own, starting over is a manual step:

1. Close SafarPro and make a backup (just in case).
2. Rename `%LOCALAPPDATA%\Nexora\SafarPro` to e.g. `SafarPro-old`.
3. Start SafarPro — you'll see the setup page again.

---

## 10. Accounting rules (what the numbers mean)

- Every money event posts a **balanced double-entry journal entry**. Posted entries can't be edited
  or deleted; a mistake is corrected with a **reversal** entry, which keeps the full history.
- A booking is invoiced (posted to Accounts Receivable and revenue) when it is **confirmed**.
  Drafts and pending bookings don't affect the books.
- Cancellations post the cancellation fee as revenue, reverse the rest through *Cancellations
  (contra-revenue)*, and record any supplier credit.
- Payment status (Paid / Partial / Overdue / Advance) and balances are calculated by the server
  from posted entries, not typed in.
- Closed periods are locked; postings into them are refused.
- Reports (P&L, balance sheet, trial balance, ageing, cash book) are built from posted journal lines.
  **Data & Backups → Ledger health** compares the receivables and payables control accounts against
  the booking and supplier sub-ledgers.

## 11. Online sync — not included

**This version is local-only.** There is no cloud sync, no multi-PC sharing and no mobile app.
The app does not pretend otherwise: there is no "synced" indicator anywhere. To share data between PCs,
use backup and restore (only one PC should be in active use at a time).

---

## 11b. Online demo for clients (optional)

The project can also run as a **public online demo** (fictional data, one-click role sign-in,
auto-reset every 24 hours) on a free PythonAnywhere account. Step-by-step guide:
[`deploy/ONLINE_DEMO.md`](../deploy/ONLINE_DEMO.md). Demo mode is off unless you turn it on there;
the Windows edition never uses it.

---

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.10 or newer was not found" | Install Python and tick *Add python.exe to PATH*. Then run setup again. |
| "Package installation failed" | Setup needs internet once. Or, on a PC with internet run `py -m pip download -r requirements.txt -d wheels`, copy the `wheels` folder next to `setup_windows.bat`, and run setup again — it will install from that folder offline. |
| "Port 8765 is used by another program — using port 8766 instead" | Another app uses the usual port, so SafarPro picked the next free one and opened the browser there. To fix the port permanently, open Command Prompt in the SafarPro folder and run `set SAFARPRO_PORT=8790` then `run_safarpro.bat`. |
| Browser didn't open | Open <http://127.0.0.1:8765/> yourself. |
| "Too many failed attempts" | Wait 5 minutes and try again. |
| Forgot the administrator password | Close SafarPro, open Command Prompt in the SafarPro folder and run `.venv\Scripts\python manage.py changepassword <username>`. |
| Need another admin from the command line | `.venv\Scripts\python manage.py create_admin` (asks for the password; nothing is hard-coded). |
| Something else | See `%LOCALAPPDATA%\Nexora\SafarPro\logs\safarpro.log`. |

---

## 13. For developers

```
safarpro/     Django settings, URLs, WSGI
core/         organization, branches, numbering, audit log, backup/restore, setup
accounts/     employees, roles and permissions, login
crm/          customers, enquiries, quotations, communications, documents
operations/   bookings, tickets, visas, Umrah/Hajj, tours, hotels, transport, suppliers, agents
finance/      chart of accounts, journal & ledger engine, payments, refunds, expenses, commissions
web/          JSON API (/api/state, /api/action/<name>), templates, static assets, tests
launch.py     starts waitress on 127.0.0.1 and opens the browser
```

Run the automated tests:

```
.venv\Scripts\python manage.py test web
```

Set `SAFARPRO_DATA_DIR` to point the app at a different data folder (for testing).

Third-party: Django (BSD), waitress (ZPL), Inter font (SIL OFL), Lucide icons (ISC).
All are bundled or installed locally; the app loads nothing from the internet.

© Nexora. Nexora SafarPro version 1.0.0.
