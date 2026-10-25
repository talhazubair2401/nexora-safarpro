#!/usr/bin/env python
"""Nexora SafarPro management entry point."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "safarpro.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Run setup_windows.bat first (it creates the .venv folder "
            "and installs the requirements)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
