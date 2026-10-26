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

# Users made while SSO was off get Keycloak accounts with their own password.
if [ "${OIDC_ENABLED:-False}" = "True" ]; then
    echo "==> Users without a Keycloak account"
    # Not fatal: without Keycloak the app still starts, and the next start
    # pushes whoever is left.
    python manage.py push_users_to_keycloak ||
        echo "WARNING: users were not pushed to Keycloak; they will be on the next start"
fi

echo "==> Starting: $*"
exec "$@"
