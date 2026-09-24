#!/bin/sh
set -e

echo "==> Migrations"
python manage.py migrate --noinput

echo "==> Baseline roles"
python manage.py seed_groups

# Only behind an explicit flag: these accounts share a well-known password.
if [ "${SEED_DEMO_USERS:-0}" = "1" ]; then
    echo "==> Demo users (SEED_DEMO_USERS=1)"
    python manage.py seed_demo_users --force
fi

echo "==> Starting: $*"
exec "$@"
