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

# Admins are not linked to Keycloak by username on sign-in; see
# accounts/management/commands/link_keycloak_user.py.
if [ -n "${KEYCLOAK_LINKS:-}" ]; then
    echo "==> Keycloak links (KEYCLOAK_LINKS)"
    python manage.py link_keycloak_user --replace $KEYCLOAK_LINKS
fi

echo "==> Starting: $*"
exec "$@"
