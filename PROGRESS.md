# Progress

Updated: 2026-10-29.

## Now: nothing open; all three assignments are done

## Done: deploy to AWS EC2 (proof for assignment #22, PR #103)

Done 2026-10-29: the stand ran at http://54.167.66.45/ (`t3.micro`, bucket
`users-and-roles-files-20261029`), proof is in `docs/deploy/` (screenshots,
`aws s3 ls`, role policy, destroy output) and linked from README. Destroyed;
AWS CLI shows nothing left. The IAM user `terraform-deploy` is deleted too, so
the keys in `~/.aws` no longer work: a new deploy needs a new IAM user.
Checked against the texts of all three tasks (users & roles, file manager,
Keycloak SSO): every requirement is covered; CI green in all 4 E2E modes.
`terraform apply/destroy` are blocked for Claude in auto mode; the user runs
them. In PowerShell quote `-var` values that contain dots. Write commit
messages with the Write tool: `Set-Content -Encoding utf8` adds a BOM.
The stand has no Keycloak on purpose (only `db` + `web`, `OIDC_ENABLED` off):
t3.micro has 1 GB RAM and OIDC needs HTTPS and a stable hostname.

The plan below is kept as a record.

The one deliverable still missing: assignment #22 wants a live link or
screenshots/video of the app working in S3 mode. README "The live stand" still
says "decommissioned" and the repo has no media.

State on 2026-10-29:
- `main` = `75b13e9`: PR #99 brought everything from `e2e-test` (Python E2E,
  review fixes, Keycloak, AD). CI on `main` is green.
- Image: `ghcr.io/senpai520120/django-application-e2e:sha-75b13e9` (public).
  Deploy that exact tag, not `latest`. The Terraform default `image` still
  points to the old repo, so always pass `-var image=...`.
- Terraform 1.16.6 and AWS CLI 2.39 are installed (winget). `terraform validate`
  in `deploy/aws` passes; local state is empty (the old stand was destroyed).
  In the VS Code terminal they may be missing from PATH until VS Code restarts:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- AWS access (done 2026-10-29): IAM user `terraform-deploy` in account
  126309363611 with `AmazonEC2FullAccess`, `AmazonS3FullAccess`, `IAMFullAccess`.
  Its access key is in `~/.aws` (`aws configure`, region `us-east-1`);
  `aws sts get-caller-identity` answers with that user. Delete this access key
  after `terraform destroy`. Never paste keys in chat.
- SSH key pair `django_application` exists in `us-east-1`; the private key is
  in the user's `.ssh` folder (`django_application.pem`).
- The user wants to stay inside the AWS free tier: destroy right after the proof.

Plan (cost: t3.micro, free tier or ~1 cent/hour; `terraform apply` only after the
user says yes):
1. `aws sts get-caller-identity` (expect `user/terraform-deploy`).
2. `cd deploy/aws && terraform apply -var region=us-east-1
   -var bucket_name=users-and-roles-files-<suffix> -var key_name=django_application
   -var image=ghcr.io/senpai520120/django-application-e2e:sha-75b13e9
   -var seed_demo_users=true` (demo accounts only for the showing).
3. Wait 2-3 min, open `app_url`. Screenshots/video:
   sign-in as `demo_admin`, `/manage/`, `/files/` with "Storage: S3FileStorage",
   create a folder + upload a file, `aws s3 ls s3://<bucket>/filemanager/ --recursive`,
   the instance IAM role policy (4 actions on one bucket), `terraform destroy` output.
4. Put them in `docs/deploy/`, link them from README "The live stand", PR to `main`.
5. `terraform destroy` with the same vars; run the README teardown checklist.

Dependabot, open question: PRs #12 and #100 were closed (localstack 3 -> 2026.x
does not start in CI; postgres 16 -> 18 fails because the 18 image wants the
volume at `/var/lib/postgresql`, not `.../data`, and needs `pg_upgrade`). Offered,
not done: ignore major updates of `postgres` and `localstack` in
`.github/dependabot.yml`, and bump `keycloak` 26.4 -> 26.8 on its own.
PR #9 (npm for the old TypeScript e2e) closed.

Permissions: auto mode does not let Claude merge or close PRs; the user does it
in the GitHub UI ("Create a merge commit", never squash: history is graded).

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
  CI has a fourth E2E run (AD) - not yet run on GitHub.

## Next

- Deploy to EC2, see "Now" above.
- Optional: turn the recorded codegen test into proper tests: start from
  `page.goto("/")`, use the fixtures (`admin_page`, `new_user`, `workspace`,
  `make_file`) and `unique_name()`, and drop the one-time Keycloak URLs.

## Known and left as is

- A Django user deleted while the Keycloak account remains is made again on
  the next sign-in. Revoke access with "Switch off" or by disabling in Keycloak.
- A timeout while the panel creates a user can leave an extra Keycloak account;
  delete it in the Keycloak console.
