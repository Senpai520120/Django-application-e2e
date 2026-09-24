#!/usr/bin/env python
"""Django command-line utility."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - guards a broken environment
        raise ImportError(
            "Could not import Django. Is it installed and available on "
            "PYTHONPATH? Did you forget to activate the virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
