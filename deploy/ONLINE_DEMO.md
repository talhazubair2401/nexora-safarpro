# Nexora SafarPro — public online demo (PythonAnywhere, free)

This puts a **demo copy** of SafarPro online so clients can try it from a link, e.g.
`https://nexora.pythonanywhere.com`. It is for showing the product only.

**What demo mode does** (it switches on only through the settings in `pythonanywhere_wsgi.py`):

- builds fictional data for **"Nexora Demo Travels"** automatically,
- sign-in page with **one-click roles**: Administrator, Branch Manager, Accountant, Visa Officer, Receptionist,
- demo accounts have **no password**, so they can't be locked or taken over,
- password changes, creating logins, suspending demo accounts and backups are **turned off**,
- the data is **wiped and rebuilt every 24 hours**, so visitors' changes don't pile up,
- server file paths are hidden, and the app says "Online demo" instead of "Local".

The Windows desktop edition never uses any of this.

---

## Steps

### 1. Create a free account
Go to <https://www.pythonanywhere.com> → **Pricing & signup** → **Create a Beginner account**.
Your **username becomes your link**: username `nexora` → `https://nexora.pythonanywhere.com`.

### 2. Upload the project
**Files** tab → **Upload a file** → choose `Nexora-SafarPro.zip`. It goes to `/home/<username>/`.

### 3. Install (Bash console)
**Consoles** tab → **Bash**. Paste these lines one at a time:

```bash
unzip -o Nexora-SafarPro.zip
mkvirtualenv --python=python3.11 safarpro
pip install "Django>=5.1,<5.2"
cd ~/Nexora-SafarPro
SAFARPRO_DEMO=1 SAFARPRO_DATA_DIR=~/safarpro-demo-data python manage.py reset_demo
```

The last line should end with **"Demo data rebuilt."**

### 4. Create the web app
**Web** tab → **Add a new web app** → Next → **Manual configuration** (not "Django") → **Python 3.11** → Next.

On the web app page, fill in:

| Section | Setting | Value |
|---|---|---|
| Virtualenv | path | `/home/<username>/.virtualenvs/safarpro` |
| Static files | URL | `/static/` |
| Static files | Directory | `/home/<username>/Nexora-SafarPro/web/static/` |
| Security | Force HTTPS | **Enabled** |

### 5. Point it at SafarPro
Still on the Web tab, click the **WSGI configuration file** link. Delete everything in it, paste the
contents of `deploy/pythonanywhere_wsgi.py`, change `USERNAME = "yourusername"` to your username, and click **Save**.

### 6. Go live
Click the green **Reload** button, then open `https://<username>.pythonanywhere.com`.
You should see **"Try the live demo"** with the five role buttons.

### 7. Keep it running (once a month)
Free web apps stop after a month unless extended. Log in and click
**Web → "Run until 1 month from today"**. It takes one click.

---

## Updating the demo later
Upload the new zip, then in a Bash console:

```bash
unzip -o Nexora-SafarPro.zip
workon safarpro
cd ~/Nexora-SafarPro
SAFARPRO_DEMO=1 SAFARPRO_DATA_DIR=~/safarpro-demo-data python manage.py reset_demo
```

and click **Reload** on the Web tab.

## If something goes wrong
- **"Something went wrong" / error page:** Web tab → **Error log** (the last lines show the cause).
- **Page has no styling:** check the Static files row in step 4 (path must end in `web/static/`).
- **"Bad Request (400)":** the username in the WSGI file doesn't match your PythonAnywhere username.
- **Reset the demo data now:** run the last command from step 3 again, then click Reload.
