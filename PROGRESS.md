# Progress

Updated: 2026-10-29.

## Now: assignments done; small open items are under "Next"

## Done: deploy to AWS EC2 (proof for assignment #22, PR #103)

Done 2026-10-29: the stand ran at http://54.167.66.45/ (`t3.micro`), proof is
in `docs/deploy/` (screenshots, `aws s3 ls`, role policy, destroy output) and
linked from README "The live stand". Destroyed; AWS CLI showed nothing left.
The IAM user used for the deploy is deleted, so the keys in `~/.aws` no longer
work: a new deploy needs a new IAM user (README "Deploying to AWS" ->
"Before the first deploy").
Checked against the texts of all three tasks (users & roles, file manager,
Keycloak SSO): every requirement is covered; CI green in all 4 E2E modes
(local, S3, Keycloak, AD).

Notes for a next deploy:
- The user wants to stay inside the AWS free tier: destroy right after the proof.
- SSH key pair `django_application` exists in `us-east-1` (a key pair belongs to
  a region); the private key is `django_application.pem` in the user's `.ssh`
  folder. Pass `-var key_name=django_application`.
- Deploy an exact image tag (`-var image=ghcr.io/senpai520120/django-application-e2e:sha-...`)
  so the stand runs a known build.
- `terraform apply/destroy` are blocked for Claude in auto mode; the user runs
  them. In PowerShell quote `-var` values that contain dots.
- Terraform and AWS CLI are installed (winget). In the VS Code terminal they may
  be missing from PATH until VS Code restarts:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- The stand has no Keycloak on purpose (only `db` + `web`, `OIDC_ENABLED` off):
  t3.micro has 1 GB RAM and OIDC needs HTTPS and a stable hostname.

Git: auto mode does not let Claude merge or close PRs; the user does it in the
GitHub UI ("Create a merge commit", never squash: history is graded). Write
commit messages with the Write tool: `Set-Content -Encoding utf8` adds a BOM.

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

## Done: Active Directory through Keycloak (PR #13, merged into `e2e-test`, then `main` via #99)

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
  The fourth E2E run in CI (AD) is green on `main`.

## Next

- Dependabot, open question: PRs #12 and #100 were closed (localstack 3 -> 2026.x
  does not start in CI; postgres 16 -> 18 fails because the 18 image wants the
  volume at `/var/lib/postgresql`, not `.../data`, and needs `pg_upgrade`).
  Offered, not done: ignore major updates of `postgres` and `localstack` in
  `.github/dependabot.yml`, and bump `keycloak` 26.4 -> 26.8 on its own.
- Optional: turn the recorded codegen test into proper tests: start from
  `page.goto("/")`, use the fixtures (`admin_page`, `new_user`, `workspace`,
  `make_file`) and `unique_name()`, and drop the one-time Keycloak URLs.

## Known and left as is

- A Django user deleted while the Keycloak account remains is made again on
  the next sign-in. Revoke access with "Switch off" or by disabling in Keycloak.
- A timeout while the panel creates a user can leave an extra Keycloak account;
  delete it in the Keycloak console.
