# Nexora SafarPro — online demo on PythonAnywhere.
#
# Paste this whole file into your PythonAnywhere WSGI configuration file
# (Web tab -> "WSGI configuration file" link), then change USERNAME below
# to your PythonAnywhere username. See deploy/ONLINE_DEMO.md.
import os
import sys

USERNAME = "yourusername"  # <-- change this

PROJECT = f"/home/{USERNAME}/Nexora-SafarPro"
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

os.environ["DJANGO_SETTINGS_MODULE"] = "safarpro.settings"
os.environ["SAFARPRO_DEMO"] = "1"                      # public demo: fictional data, auto-reset
os.environ["SAFARPRO_DEMO_RESET_HOURS"] = "24"         # rebuild the demo data once a day
os.environ["SAFARPRO_DATA_DIR"] = f"/home/{USERNAME}/safarpro-demo-data"
os.environ["SAFARPRO_ALLOWED_HOSTS"] = f"{USERNAME}.pythonanywhere.com"
os.environ["SAFARPRO_HTTPS"] = "1"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
