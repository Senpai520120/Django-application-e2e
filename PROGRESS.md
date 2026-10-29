# Progress

Updated: 2026-10-28.

## Done: sign-in through Keycloak (SSO)

PR #11 (`feature/keycloak-sso`) is merged into `e2e-test`, with CI green in all modes.

- SSO is optional: `OIDC_ENABLED`, off by default. Start it with
  `docker compose -f docker-compose.yml -f docker-compose.sso.yml up -d --build --wait`.
- Keycloak answers "who you are"; roles and switching a user off stay in `/manage/`.
- A Keycloak account is linked to a Django user by its `sub` (`accounts.KeycloakIdentity`).
  Only users without admin rights are linked by username on the first sign-in;
  admins are linked with `manage.py link_keycloak_user` or `KEYCLOAK_LINKS`.
- Users made in the app get Keycloak accounts with the same password (Keycloak
  takes Django's `pbkdf2_sha256` hashes): at once from the panel with SSO on, or
  on the next start in SSO mode for users made while it was off.
- Dev Keycloak forgets its data on `down`; `KEYCLOAK_REMAKE_LOST_ACCOUNTS=True`
  (dev compose only) makes the lost accounts again on start.
- A user disabled in Keycloak is signed out within 15 minutes (SessionRefresh).
- Keycloak console: http://localhost:8080/admin, `admin` / `admin`.
  All demo and `test_*` accounts: `demo-password-123`.

Tests: 228 unit tests, coverage 93%. E2E with `E2E_AUTH=keycloak`: 42 passed,
8 skipped (tests of the app's own sign-in form).

## In progress: Active Directory through Keycloak (branch `feature/active-directory`, pushed, no PR yet)

- `docker-compose.ad.yml` over SSO adds Samba AD DC (`CORP.EXAMPLE.TEST`, image
  from `docker/samba/`) and switches on the realm's LDAP provider (read only,
  LDAPS, Keycloak trusts Samba's own certificate from the `samba-tls` volume).
- Roles stay in Django (variant A). Keycloak: one account per email
  (`duplicateEmailsAllowed: false`), sign-in by email allowed.
- First sign-in links by verified email, then by username; same name with
  another email is refused. `push_users_to_keycloak` and the panel make no
  Keycloak account for people Keycloak finds in AD (`in_directory`).
- Realm has the `autoforyou` client; network `sso-shared` lets other stacks
  reach `keycloak:8080`. Task for AUTOforYOU:
  `D:\pyCharm\AUTOforYOU\docs\tasks\sso-1-keycloak-ad.md` (Opus session).
- Session and CSRF cookies have the app's own names (`users_roles_sessionid`,
  `users_roles_csrftoken`): AUTOforYOU on localhost overwrote Django's default
  ones and Sign out failed with CSRF 403. E2E TC-57..59 cover it.
- Checked: 242 unit tests, coverage 93%; E2E SSO 45, AD 50 passed.
  CI has a fourth E2E run (AD) - not yet run on GitHub.

## Next

- Merge `e2e-test` into `main` in a separate PR. `main` still has the old
  TypeScript tests, so it takes every commit since PR #4, not only SSO.
- Optional: turn the recorded codegen test into proper tests: start from
  `page.goto("/")`, use the fixtures (`admin_page`, `new_user`, `workspace`,
  `make_file`) and `unique_name()`, and drop the one-time Keycloak URLs.

## Known and left as is

- A Django user deleted while the Keycloak account remains is made again on
  the next sign-in. Revoke access with "Switch off" or by disabling in Keycloak.
- A timeout while the panel creates a user can leave an extra Keycloak account;
  delete it in the Keycloak console.
