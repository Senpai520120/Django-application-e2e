# Users & Roles

Users sign in through Django's built-in views, and an admin manages the list of
users and roles from a page of its own at `/manage/` — not through `/admin/` —
granting and revoking roles there.

A user is the stock `auth.User`, a role is the stock `auth.Group`, and login,
logout, password hashing and sessions all come from `django.contrib.auth`.
What is written by hand: the panel, the access control and the templates.

## Stack

| What | With |
| --- | --- |
| Language | Python 3.11+ (developed on 3.11, CI runs 3.12 and 3.13) |
| Framework | Django 5.2 LTS |
| Database | PostgreSQL in docker and CI, SQLite by default locally |
| Frontend | Django templates (SSR) plus a single CSS file |
| Authentication | `django.contrib.auth`, sessions, built-in `LoginView` / `LogoutView` |
| Roles | built-in `auth.Group` |
| File storage | `FileSystemStorage` or S3 through django-storages, picked by an environment variable |
| Configuration | `django-environ`, everything from the environment |
| Tests | pytest + pytest-django, coverage at least 90% (enforced by CI) |
| Lint | ruff + black, run by hand and in CI |
| E2E | pytest + Playwright (chromium), sign-in, panel and file manager scenarios, also through Keycloak and Active Directory |
| CI/CD | GitHub Actions: linters → Django checks → tests → docker compose smoke → image published to GHCR |

## Quick start

Python is all you need. The default database is SQLite, so nothing else has to
be installed.

```bash
# 1. Virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Dependencies
pip install -r requirements-dev.txt   # production only needs requirements.txt

# 3. Settings: copy the example and put in a SECRET_KEY
cp .env.example .env                  # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # paste into SECRET_KEY

# 4. Database: migrations create the admin and user roles right away
python manage.py migrate

# 5. Your own administrator account
python manage.py createsuperuser

# 6. Demo users: an admin, a regular one, a deactivated one and a dozen more
python manage.py seed_demo_users

# 7. Run it
python manage.py runserver
```

Check:

* http://127.0.0.1:8000/login/ — sign in;
* http://127.0.0.1:8000/ — "you are signed in as X, your roles are …";
* http://127.0.0.1:8000/manage/ — the panel (admins only).

A superuser reaches the panel straight away. To make a regular user an admin,
add them to the `admin` group, either from the panel itself or with:

```bash
python manage.py shell -c "from django.contrib.auth.models import Group, User; User.objects.get(username='ivan').groups.add(Group.objects.get(name='admin'))"
```

## Demo users

```bash
python manage.py seed_demo_users              # create or update
python manage.py seed_demo_users --extra 0    # without the crowd used for pagination
python manage.py seed_demo_users --password 'My-Pass-1' --extra 5
python manage.py seed_demo_users --delete     # remove every demo_*
```

The command is idempotent: running it again creates no duplicates and instead
returns the accounts to the described state (password, roles, flags). With
`DEBUG=False` it refuses to run without `--force`, so accounts with a well-known
password never reach production.

| Username | Role | What it is for |
| --- | --- | --- |
| `demo_admin` | `admin` group | an admin the ordinary way, sees `/manage/` |
| `demo_staff` | `is_staff` | the second route into the panel, with no group |
| `demo_user` | `user` group | a regular user, gets 403 on `/manage/` |
| `demo_inactive` | `user` group | deactivated, cannot sign in |
| `demo_user01…10` | `user` group | a crowd for search and pagination |

They all share the password `demo-password-123` (changed with `--password`).

## Routes

| URL | What it does | Who gets in |
| --- | --- | --- |
| `/login/` | sign in, the built-in `LoginView` with our template | everyone |
| `/logout/` | sign out, the built-in `LogoutView` (POST only) | everyone |
| `/` | home page: who you are and which roles you hold | signed in |
| `/files/` | file manager: folder listing and navigation | signed in |
| `/files/folder/new/` | create a folder (POST) | signed in |
| `/files/upload/` | upload files (POST) | signed in |
| `/files/rename/` | rename a file or a folder | signed in |
| `/files/delete/` | delete with confirmation | signed in |
| `/files/download/` | download a file as an attachment | signed in |
| `/manage/` | user list: search, pagination, roles, activity | admins |
| `/manage/roles/` | roles and their member counts | admins |
| `/manage/users/<pk>/roles/` | form for granting and revoking roles | admins |
| `/manage/users/<pk>/toggle-active/` | switch a user on or off (POST) | admins |
| `/manage/users/new/` | create a user (bonus) | admins |
| `/manage/audit/` | who changed whose role, and when (bonus) | admins |
| `/admin/` | Django's stock admin, kept for reference | `is_staff` |

An anonymous visitor on `/manage/` is redirected to `/login/?next=…`; a signed-in
non-admin gets **403**.

## Environment variables

They are read from `.env` in the project root (see `.env.example`). Real
environment variables win over the file, so CI and docker need no `.env` at all.

| Variable | Default | What for |
| --- | --- | --- |
| `SECRET_KEY` | — (required) | Django key; without it the project refuses to start |
| `DEBUG` | `False` | debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | comma-separated list |
| `DATABASE_URL` | `sqlite:///<root>/db.sqlite3` | for example `postgres://user:pass@host:5432/db` |
| `TIME_ZONE` | `UTC` | time zone |
| `STATICFILES_BACKEND` | whitenoise manifest when `DEBUG=False` | how static files are served |
| `SESSION_COOKIE_SECURE` | `False` | turn on over HTTPS only |
| `CSRF_COOKIE_SECURE` | `False` | turn on over HTTPS only |
| `SECURE_SSL_REDIRECT` | `False` | redirect to HTTPS |
| `SECURE_HSTS_SECONDS` | `0` | HSTS |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | HSTS for subdomains |
| `SECURE_HSTS_PRELOAD` | `False` | HSTS preload |
| `USE_X_FORWARDED_PROTO` | `False` | trust `X-Forwarded-Proto` from the proxy |
| `LOG_LEVEL` | `INFO` | log level on stdout |
| `FILE_STORAGE_BACKEND` | `local` | `local` is the server disk, `s3` is an AWS bucket |
| `FILE_MANAGER_ROOT` | `<root>/filemanager` | storage folder when `local` |
| `FILE_MANAGER_MAX_FILE_SIZE` | `26214400` | per-file limit, in bytes |
| `FILE_MANAGER_MAX_TOTAL_SIZE` | `536870912` | whole-storage limit, in bytes |
| `FILE_MANAGER_S3_LOCATION` | `filemanager` | key prefix inside the bucket |
| `AWS_STORAGE_BUCKET_NAME` | empty | bucket, required with `s3` |
| `AWS_S3_REGION_NAME` | `eu-central-1` | bucket region |
| `AWS_S3_ENDPOINT_URL` | empty | S3 emulator address for local checks |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | empty | left unset on EC2, where the IAM role works |
| `CSRF_TRUSTED_ORIGINS` | empty | needed behind an HTTPS proxy |

The `*_SECURE` flags are off by default: over plain local HTTP the browser drops
a secure cookie and login stops working. Turn them on before going to HTTPS and
check with `python manage.py check --deploy`.

## What comes from the box, and what is written by hand

Out of the box (never rewritten):

| Capability | From |
| --- | --- |
| User model | `django.contrib.auth.models.User` |
| Roles | `django.contrib.auth.models.Group` |
| Password hashing | `PBKDF2-SHA256`, `set_password` / `check_password` |
| Password validation | `AUTH_PASSWORD_VALIDATORS` |
| Login and logout | `auth.views.LoginView`, `auth.views.LogoutView` |
| Login form and its error messages | `AuthenticationForm` |
| Sessions | `django.contrib.sessions` |
| CSRF | `CsrfViewMiddleware` plus `{% csrf_token %}` |
| Access-control scaffolding | `LoginRequiredMixin`, `UserPassesTestMixin` |
| Lists, forms, pagination | `ListView`, `UpdateView`, `CreateView`, `Paginator` |
| Creating a user as an admin | `UserCreationForm` (we only added fields) |
| Migrations, ORM, management commands | Django |

Written by hand:

| File | What is in it |
| --- | --- |
| `accounts/permissions.py` | `is_admin()` — the single definition of "who is an admin" |
| `accounts/mixins.py` | `AdminRequiredMixin` — access control for every panel view |
| `accounts/context_processors.py` | the `is_panel_admin` flag for templates |
| `accounts/views.py` | the user's home page |
| `accounts/urls.py` | wiring up the built-in `LoginView` / `LogoutView` |
| `accounts/migrations/0001_seed_groups.py` | data migration: the `admin` and `user` roles |
| `accounts/management/commands/seed_groups.py` | idempotent role seeding |
| `accounts/management/commands/seed_demo_users.py` | demo users for local checks |
| `docker/entrypoint.sh` | the container start-up sequence |
| `panel/views.py` | views of the `/manage/` panel |
| `panel/forms.py` | the roles form and the user creation form |
| `panel/models.py` | `RoleChange` — the audit log of role changes (bonus) |
| `files/paths.py` | path and name normalisation, protection from traversal |
| `files/storage.py` | the storage contract and two implementations: disk and S3 |
| `files/access.py` | the access rule for the files section |
| `files/views.py` | listing, upload, rename, delete, download |
| `e2e/` | pytest + Playwright: sign-in, panel and file manager scenarios in a browser |
| `deploy/aws/` | Terraform: bucket, IAM role, instance |
| `templates/` | every template, including `registration/login.html` and 403/404/500 |
| `config/settings.py` | settings on top of `django-environ` |
| `config/settings_test.py` | settings for the test suite |
| `.github/workflows/ci.yml` | the CI/CD pipeline |

## Roles and access control

A role is a group. Seeding creates two of them: `admin` and `user`.

An admin is whoever satisfies `accounts.permissions.is_admin`: a member of the
`admin` group, **or** someone with `is_staff`, **or** a superuser. That is the
only place the rule lives; views, templates and tests all go through it.

Every panel view inherits from `AdminRequiredMixin`, so no check is copy-pasted:

```python
class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self) -> bool:
        return is_admin(self.request.user)
```

The behaviour comes from the stock `AccessMixin`: an anonymous visitor is
redirected to login with `?next=`, a signed-in non-admin gets `PermissionDenied`,
that is 403. Permissions are checked on every request, so a revoked role closes
the panel immediately, without signing out and back in.

## File manager

The `/files/` section: a tree of folders and files, folder creation, uploading
several files at once, renaming, downloading and deleting with confirmation.
The storage is switched by an environment variable, and the views know nothing
about it.

**Who may open it.** Every signed-in user: this is a section shared by the whole
team rather than a part of the admin panel, which is why it lives next to
`/manage/` rather than inside it. The rule is isolated in `files/access.py` — to
hand the files to admins only, swap the base class there for
`AdminRequiredMixin`.

### How the storage is built

```
files/storage.py
├── FileManagerStorage   contract: list_dir, make_dir, save, open, delete,
│                        rename, exists, is_dir, size, total_size
├── LocalFileStorage     on top of FileSystemStorage
└── S3FileStorage        on top of S3Storage from django-storages
```

The backend lives in `STORAGES["filemanager"]` in the settings, next to
`STORAGES["default"]`, and Django's own storage registry builds it;
`get_storage()` only fetches it. `FILE_STORAGE_BACKEND` fills it in the same
way `DATABASE_URL` picks a database: `local`, `s3`, or the dotted path of any
other `FileManagerStorage` subclass. A third backend is therefore one new
class plus `FILE_STORAGE_BACKEND=yourapp.storage.YourStorage`: `files/storage.py`,
the views and the templates stay as they are.

Folders in S3 are virtual: an empty folder is a zero-length object whose key
ends with `/`. Deleting a folder removes every key under its prefix; renaming
copies them onto the new prefix and deletes the old ones.

### S3 mode

```bash
# in .env
FILE_STORAGE_BACKEND=s3
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=eu-central-1
```

The keys can be left out when the app runs on EC2 with an IAM role: boto3 picks
up temporary credentials from the instance metadata. To exercise S3 mode locally
without a cloud, lay `docker-compose.s3.yml` over the main file. It adds
LocalStack, which makes the bucket on every start, and sets the S3 variables
itself, so `.env` stays as it is:

```bash
docker compose -f docker-compose.yml -f docker-compose.s3.yml up -d --build --wait
```

### Security

| What | How it is closed |
| --- | --- |
| Path traversal | `files/paths.py`: `..`, absolute paths, drive letters and null bytes are rejected before the storage is touched, and the answer is 400 |
| Symlink leading out | the local storage additionally compares the already resolved path with the root |
| File names | separators, control characters and names reserved by Windows are forbidden, and length is capped at 120 characters |
| Size | a per-file limit enforced while the file arrives: `files/uploads.py` stops reading a file once it passes the limit, so an oversized upload never reaches the disk. A total-storage limit is checked before saving; it is a soft limit (no lock), so uploads at the very same moment can overshoot it by one batch each. Both come from the environment |
| Dangerous extensions | a download always carries `Content-Disposition: attachment` plus `X-Content-Type-Options: nosniff`, so the browser never executes an `.html` or an `.svg` |
| Overwriting | a file with an existing name is not silently overwritten but answered with an error |
| Forged parent | a new file or folder goes only into an existing folder; `notes.txt/new` is refused the same way by both backends |
| Secrets | AWS keys live only in `.env` and in the IAM role; the repository holds none |

Every line above is covered by tests: `tests/test_files_paths.py`,
`tests/test_files_storage.py`, `tests/test_files_views.py`.

## Tests

```bash
pytest                                  # every test in tests/
pytest -v
pytest --cov --cov-report=term-missing  # coverage; below 90% fails, as in CI
```

The suite uses `config/settings_test.py`: its own `SECRET_KEY`, static files
without a manifest, and a fast password hasher. That is why `pytest` works on a
fresh clone with no `.env` and no `collectstatic`. The production hasher is
verified by a separate test that switches `PBKDF2PasswordHasher` on explicitly.

What is covered:

* `tests/test_auth.py` — successful and failed sign-in, no leak of "does this
  user exist", an inactive user, logout, the redirect for an unauthenticated
  visitor, and **the password stored in `auth_user` as a hash** (read with raw
  SQL);
* `tests/test_access_control.py` — anonymous → redirect, regular user → 403,
  `admin` group / `is_staff` / superuser → 200, revoking a role closes access;
* `tests/test_roles.py` — granting and revoking a role changes the database and
  writes an audit record, a stranger is refused, a POST without a CSRF token is
  rejected;
* `tests/test_panel.py` — search, pagination, activation and deactivation, user
  creation, the audit page;
* `tests/test_seed_groups.py` — roles appear after `migrate`, and the
  `seed_groups` command is idempotent;
* `tests/test_seed_demo_users.py` — demo users are created with the right roles
  and flags, the command is idempotent, `--delete` leaves other accounts alone,
  and with `DEBUG=False` it refuses to run without `--force`;
* `tests/test_files_paths.py` — path traversal in every shape, name sanitisation;
* `tests/test_files_storage.py` — **the storage contract, run twice**: against
  the local disk and against S3 through `moto`. The same set of checks, two
  different implementations;
* `tests/test_files_views.py` — anonymous access, size limits, the attachment
  header on download, recursive deletion, and 400 on a path leading outside;
* `tests/test_oidc.py` — sign-in through Keycloak with its answers faked:
  linking by `sub`, never linking admins by name, refused and disabled users,
  sign-out ending the Keycloak session;
* `tests/test_keycloak_admin.py` — the Admin API calls with HTTP faked:
  accounts made with the Django password hash, password changes, Keycloak
  being down.

The test environment lives in `config/settings_test.py`; the user fixtures are in
`tests/conftest.py`.

## Sign-in through Keycloak (SSO)

Off by default. `docker-compose.sso.yml` adds Keycloak with the realm from
`keycloak/realm-myapp.json` and turns `OIDC_ENABLED` on:

```bash
docker compose -f docker-compose.yml -f docker-compose.sso.yml up -d --build --wait
```

Then `/login/` leads to the Keycloak form at `localhost:8080`, and signing in
there signs in to every app of the realm (the account page
`http://localhost:8080/realms/myapp/account` opens without a second form).
"Sign out" ends the Keycloak session too. Keycloak admin console:
`http://localhost:8080/admin`, `admin` / `admin`.

**Who decides what.** Keycloak answers "who you are": password, disabled
accounts, the shared session. The app keeps "what you may do": roles are still
given in `/manage/` and written to the audit log, and a user switched off in
the panel stays out even with a valid Keycloak password (they land on
`/login/failed/`). A user who exists only in Keycloak gets the `user` role on
the first sign-in.

**How a Keycloak account finds its Django user.** By Keycloak's permanent id
(`sub`), kept in `accounts.KeycloakIdentity`, so renaming an account in
Keycloak changes nothing in the app. On the very first sign-in an existing
Django user is linked: first by email, when Keycloak vouches for it
(`email_verified`, as for everyone from Active Directory), then by the same
username (case aside), which is how the `demo_*` accounts become the same
people on both sides. The same name with another email is another person and
is refused. Never linked by name or email:
a user already linked to another Keycloak account, and anybody with admin
rights (the `admin` role, staff, superusers), since whoever first signed in
under that name would get those rights. Admins are linked by hand with the
Keycloak account id (the "ID" on the user's page in the Keycloak console):

```bash
python manage.py link_keycloak_user olga=2b0f5c1e-...           # several pairs allowed
python manage.py link_keycloak_user --replace olga=<new id>     # account recreated in Keycloak
```

In docker the same runs on start from `KEYCLOAK_LINKS`; that is how
`demo_admin` (its id is fixed in the realm file) is linked.

**Users made in the app get Keycloak accounts.** With SSO on, "New user" in
`/manage/` creates the Keycloak account too, with the same password; if
Keycloak is down or already has that username, nobody is created and the form
says why. Users made while SSO was off get their accounts on the next start
in SSO mode (`manage.py push_users_to_keycloak`, run by the entrypoint), and
sign in with their old password. This works because Keycloak accepts Django's
`pbkdf2_sha256` password hashes as they are: the app never sees or sends a
plain password. The app calls Keycloak's Admin API as the service account of
its `django-app` client, which may only view and manage users. Email and name
are optional in the realm, as in the panel.

**A password changed in Django goes to Keycloak too**, the same way, as a
hash: whatever changed it (`/admin/`, `manage.py changepassword`, a shell),
saving the user sends the new hash once the change is committed
(`accounts/signals.py`). If Keycloak is down then, the change in Django stays
and the error is logged; Keycloak keeps the old password until the next
change. People from Active Directory change their password in AD.

Not synced: switching a user off (the app refuses them anyway), and names
and emails changed later.

**When Keycloak loses accounts.** This development Keycloak keeps its data
inside its container, so after `docker compose down` it has only the realm
file again. With `KEYCLOAK_REMAKE_LOST_ACCOUNTS=True` (set in
`docker-compose.sso.yml`) the app makes the lost accounts again on start, with
the users' current passwords. Leave it off in production: there an account
missing in Keycloak was deleted on purpose, and the app only reports it.

**Disabled in Keycloak while signed in.** Every 15 minutes
(`OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS`) the app silently asks Keycloak again
about a signed-in user; someone disabled or deleted there is signed out then.
Switching a user off in the panel works at once. With SSO on there
are no local passwords at all, the `/admin/` form included: Keycloak is the
only way in, and a user switched off in the panel loses their session at once.

Accounts in the realm, all with the password `demo-password-123`:

| Username | In Keycloak | In the app |
| --- | --- | --- |
| `demo_admin`, `demo_user` | enabled | as in [Demo users](#demo-users) |
| `demo_inactive` | enabled | switched off: Keycloak lets in, the app does not |
| `kc_disabled` | disabled | — |
| `kc_newcomer`, `kc_promoted` | enabled | appear on the first sign-in |

The secret `dev-only-secret` is for local runs only. The app talks to Keycloak
at two addresses (`OIDC_BROWSER_URL` for the browser, `OIDC_BACKEND_URL` from
inside docker); outside docker both are the same and only the first is needed.

E2E in this mode: `pytest e2e` (the mode is detected). The fixtures sign in through
the Keycloak form, tests of the app's own form are skipped, and
`e2e/tests/test_sso.py` runs (TC-44…51).

**One person, one email.** The realm lets no two accounts share an email
(`duplicateEmailsAllowed: false`), and the email works as the username on the
form. Other apps of the realm can rely on it to find their own users: the
realm also has the `autoforyou` client, and its containers reach Keycloak at
`http://keycloak:8080` through the shared docker network `sso-shared`.

## Active Directory through Keycloak

`docker-compose.ad.yml`, laid over SSO, adds a test domain controller (Samba,
domain `CORP.EXAMPLE.TEST`) and switches on the `active-directory` provider of
the realm (Keycloak's User Federation over LDAPS, read only):

```bash
docker compose -f docker-compose.yml -f docker-compose.sso.yml   -f docker-compose.ad.yml up -d --build --wait
```

The first start makes the domain and takes about a minute.

- **AD decides who you are.** Keycloak checks the password against AD on every
  sign-in: a password reset or an account disabled in AD counts at once. People
  and passwords are managed in AD only; Keycloak and the app do not write there.
- **The app decides what you may do**, as with plain SSO: roles in `/manage/`.
  Someone from AD gets the `user` role on the first sign-in.
- **No second account for people in AD.** `push_users_to_keycloak` and "New
  user" in the panel ask Keycloak first: a username or email it finds in AD
  gets no Keycloak account of its own. The panel still makes the Django user
  (give them roles ahead) and says they are in Active Directory; their first
  AD sign-in lands in that user, found by email, or by the username.
- **TLS.** Samba makes a certificate for the name `samba` on its first start
  and keeps it in the `samba-tls` volume; Keycloak trusts exactly that one
  (`KC_TRUSTSTORE_PATHS`). In production give Keycloak the CA of the real
  domain controllers instead.

Test accounts (password `demo-password-123`): `ad_alice`, `ad_bob`, and
`ad_disabled`, which is disabled in AD. Domain administrator:
`Administrator` / `Samba-admin-123`; Keycloak reads AD as `svc-keycloak`.
All of them are for this test domain only. LDAPS is published on
`127.0.0.1:6636` for the tests.

Two things that differ from a real domain on purpose: the domain lives in the
container and is made again after `down` (people get new ids then, and with
`KEYCLOAK_REMAKE_LOST_ACCOUNTS` the app drops the old links so the next
sign-in links them again), and the old password stops working at once after
a change (AD normally allows it for another hour: `old password allowed
period`).

E2E in this mode: `pytest e2e` (the mode is detected): everything of the SSO mode plus
`e2e/tests/test_ad.py` (TC-52…56), which adds people to AD over LDAPS as the
domain administrator would (`e2e/directory.py`).

## E2E tests (Playwright)

Pytest checks the backend and the views; Playwright checks that the scenario
works in a real browser. Neither replaces the other.

The browser tests are written in Python with pytest and
[pytest-playwright](https://playwright.dev/python/). They have their own
requirements and their own `e2e/pytest.ini`, so a plain `pytest` still runs
only the unit tests, and the two never mix.

```bash
pip install -r e2e/requirements.txt
python -m playwright install chromium
pytest e2e                                  # against a running stack on :8000
pytest e2e --base-url http://host:port      # against another copy of the app
pytest e2e --browser firefox --browser webkit
pytest e2e --headed --slowmo 500            # watch it in a real window
```

The app under test is started by the same `docker compose` as usual. The tests
sign in as the `seed_demo_users` accounts (`demo_admin`, `demo_user`,
`demo_inactive`) with the password above, overridable through `E2E_PASSWORD`.
`E2E_MAX_FILE_SIZE` must match the app's `FILE_MANAGER_MAX_FILE_SIZE`
(5 MB in docker-compose).

Without Docker, a dev server works too:

```bash
export DATABASE_URL=sqlite:///e2e.sqlite3 FILE_MANAGER_MAX_FILE_SIZE=5242880 DEBUG=True
python manage.py migrate && python manage.py seed_groups && python manage.py seed_demo_users --force
python manage.py runserver 127.0.0.1:8000
```

```
e2e/
├── pytest.ini         base URL, trace/screenshot/video kept for failed tests
├── requirements.txt   pytest + pytest-playwright
├── config.py          base URL, demo accounts, size limit (all from env)
├── conftest.py        signed-in tabs, a fresh user per test, a workspace
│                      folder per file test, cleanup after each test
├── helpers.py         unique names, sign-in, sending a form straight to the server
├── pages/             Page Objects: login, home, users, roles, audit, files
├── docs/test-cases.md TC-01 … TC-60, the description of every scenario
├── tools/             test_cases.json (the source of the cases) and a script that
│                      writes docs/test-cases.md or opens "Test case" issues:
│                      cd e2e && python tools/create_test_case_issues.py --markdown
└── tests/
    ├── test_login.py     sign-in, wrong password, unknown and inactive user, sign-out
    ├── test_access.py    who reaches /manage/ and /files/, forms sent directly
    ├── test_users.py     search, create, weak password, switching a user off
    ├── test_roles.py     grant and revoke a role, self-lockout ban, audit log
    ├── test_folders.py   create, nest, breadcrumbs, duplicates, delete
    ├── test_files.py     upload, rename, download, delete, the size limit
    ├── test_sso.py       the Keycloak form, single sign-on and sign-out (SSO stack)
    └── test_ad.py        Active Directory people signing in through Keycloak (AD stack)
```

Every file test works in a folder of its own with a unique name and deletes it
afterwards; role and deactivation tests work on a brand-new user per test.
Runs depend neither on each other nor on order. Failed tests leave a trace,
a screenshot and a video in `test-results/` (`playwright show-trace <zip>`).

The whole project speaks English: interface, comments, test names and docs.
`LANGUAGE_CODE` is `en-us`, so Django's own messages — login errors, password
validators — come out in English too, and the tests assert those exact texts.
Two non-ASCII cases are kept on purpose: one upload scenario uses a Cyrillic
file name, and `tests/test_files_paths.py` keeps Cyrillic fixtures, so that
path handling is still proven against non-ASCII input.

## Lint and formatting

```bash
ruff check .            # check
ruff check --fix .      # fix automatically
black .                 # format
black --check .         # check only, the way CI does
```

Nothing runs these for you before a commit: the project has no git hooks.
Run them yourself, or rely on CI, which does both on every pull request.

Two more checks worth running before pushing, because CI runs them too:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run   # catches forgotten migrations
```

## CI/CD

`.github/workflows/ci.yml` runs on every push to `main`, on every pull request
and from the button (`workflow_dispatch`). Six jobs:

| Job | What it does |
| --- | --- |
| **Linters** | `ruff check` and `black --check` over the whole repository |
| **Django checks** | `manage.py check`, `makemigrations --check` (forgotten migrations), `check --deploy --fail-level WARNING` with the HTTPS flags on |
| **Tests** | a matrix of Python 3.12 and 3.13, a real PostgreSQL 16 service container, `pytest --cov --cov-fail-under=90`, coverage report in the artifacts |
| **docker compose up** | starts the stack the way production does and checks the 302 for anonymous visitors on `/manage/` and `/files/`, an admin sign-in, and that the roles are seeded |
| **E2E (Playwright)** | starts the same stack, installs chromium, runs `pytest e2e` four times — local storage, S3 (localstack), sign-in through Keycloak, Active Directory behind Keycloak — and on failure keeps traces, screenshots and videos as an artifact |
| **Publish to GHCR** | waits for a green smoke and E2E; for `main` and `v*` tags only: builds the image and pushes it to `ghcr.io/<owner>/<repo>` with the `latest`, `sha-…` and semver tags. Uses the built-in `GITHUB_TOKEN`, so no secrets to configure |

CD goes as far as publishing the image: after that, `docker compose pull &&
docker compose up -d` with that image is enough on your own server. Dependency
updates come from `.github/dependabot.yml` (pip for the app and for e2e, GitHub Actions, Docker and
docker-compose, weekly).

## PostgreSQL instead of SQLite

One variable in `.env` is enough:

```
DATABASE_URL=postgres://users_roles:users_roles@localhost:5432/users_roles
```

The `psycopg[binary]` driver is already in `requirements.txt`; after that it is
the usual `python manage.py migrate`.

## Docker

```bash
cp .env.example .env     # SECRET_KEY is required, compose overrides the rest
docker compose up --build
```

Postgres and the application come up on http://127.0.0.1:8000/. Everything the
start needs is done by `docker/entrypoint.sh`:

1. `migrate` — the schema and the `admin` / `user` roles (created by the data
   migration);
2. `seed_groups` — in case a role was deleted by hand;
3. `seed_demo_users` — **only if** `SEED_DEMO_USERS=1`;
4. `collectstatic` — static files for whitenoise;
5. `exec` into the command from `CMD`, that is gunicorn.

The flag is on in `docker-compose.yml`, so right after `up` you can sign in as
`demo_admin` / `demo-password-123`. For a production run drop the variable or
set it to `"0"` — inside the image the seeding is off by default, and accounts
with a known password have no business in production.

Use `--build` after every `git checkout` or `git pull`. Plain
`docker compose up -d` restarts the **existing** container, which may have been
built from older code, and then you end up debugging code that is not running.

```bash
docker compose exec web python manage.py createsuperuser   # your own account
docker compose logs -f web                                 # logs, start-up steps included
```

Static files are collected while the image is built, dependencies are installed
from `requirements.lock` (generated by `pip-compile requirements.txt`), and the
process inside the container runs as the unprivileged `app` user.

The `migrate` call in the entrypoint assumes a single instance: with several
replicas they would all start at once and nobody arbitrates the race for
migrations. This is a deliberate simplification — in production migrations are
run as a separate deployment step.

### What happens to the data

The database lives in the named volume `pgdata` rather than inside the
container, which means:

| Command | What happens to the data |
| --- | --- |
| `docker compose stop` / `restart` | kept |
| `docker compose down` | kept (only containers are removed) |
| `docker compose up` after the machine was switched off | kept |
| `docker compose down -v` | **deleted along with the volume** |

So the data can only disappear through an explicit `-v`. On the next start the
entrypoint runs the migrations and the seeding again: on an empty database that
gives a clean stand, and on an existing one nothing breaks, because both
commands are idempotent.

## Deploying to AWS

The whole application is deployed — `/manage/`, `/files/` and the rest — not the
file manager on its own.

### What is created

| Service | What for |
| --- | --- |
| S3 | storage for the file manager: a private bucket with encryption and public access blocked |
| EC2 (t3.micro, free tier) | an instance with Docker; it pulls the image from GHCR and brings it up together with Postgres |
| Instance IAM role | access to the one bucket limited to `ListBucket`, `GetBucketLocation`, `GetObject`, `PutObject`, `DeleteObject` — no keys in the code and no `AdministratorAccess` |
| Security group | only port 80 is open outward; SSH only if you name your own address |

```
browser → EC2 (:80 → gunicorn:8000) ─┬→ Postgres in a container on the same instance
                                     └→ S3 (files), reached by IAM role, IMDSv2
```

### The live stand

Deployed on 2026-10-29 and verified end to end: the application worked and
files went into S3. Then the stand was torn down to stay inside the free tier,
so the address below no longer answers. The proof is kept in
[docs/deploy/](docs/deploy/).

| | |
| --- | --- |
| Address | http://54.167.66.45/ (decommissioned) |
| Demo account | `demo_admin` existed only on that stand (it ran with `seed_demo_users=true`) and is gone with it |
| Region | `us-east-1` |
| Bucket | `users-and-roles-files-20261029` |
| Image | `ghcr.io/senpai520120/django-application-e2e:sha-75b13e9` |

| Proof | What it shows |
| --- | --- |
| [01-sign-in.png](docs/deploy/01-sign-in.png) | the sign-in page on the stand |
| [02-manage.png](docs/deploy/02-manage.png) | `/manage/` as `demo_admin` |
| [03-files-s3-upload.png](docs/deploy/03-files-s3-upload.png) | `/files/` with `Storage: S3FileStorage`, a folder made and a file uploaded |
| [04-s3-and-iam.txt](docs/deploy/04-s3-and-iam.txt) | the same folder and file in the bucket (`aws s3 ls`) and the instance role policy limited to that one bucket |
| [05-terraform-destroy.txt](docs/deploy/05-terraform-destroy.txt) | the teardown: 10 resources destroyed, nothing left in the account |

### Before the first deploy

1. In the AWS console create an IAM user for Terraform (no console access)
   with `AmazonEC2FullAccess`, `AmazonS3FullAccess` and `IAMFullAccess`, and
   an access key for it. Never commit the key or paste it anywhere.
2. `aws configure` with that key and the region you deploy to (`us-east-1`).
3. `aws sts get-caller-identity` must name that user.
4. In EC2 → Key Pairs of the same region, create a key pair; its name goes
   into `-var key_name=...`.

After `terraform destroy`, delete the access key (or the whole user) too.

### Steps

```bash
cd deploy/aws
terraform init
terraform apply   -var region=us-east-1   -var bucket_name=your-globally-unique-bucket   -var key_name=your-key-pair-name   -var ssh_cidr=your.ip.address/32   -var image=ghcr.io/senpai520120/django-application-e2e:sha-75b13e9
```

The `demo_*` accounts share a password published in this README, so they are
**not** created by default: the stand is reachable from the internet over plain
HTTP. Sign in with your own administrator instead
(`docker compose exec web python manage.py createsuperuser` over SSH), or add
`-var seed_demo_users=true` for a short-lived demo and destroy the stand
afterwards.

A key pair belongs to a region, so deploy into the same region where it was
created. The `terraform.tfstate` file holds the generated `SECRET_KEY` and the
database password — it is in `.gitignore`, and it must never be committed or
passed around.

Terraform prints `app_url`, and that is where the application opens. The first
start takes a couple of minutes while the instance installs Docker and pulls the
image. The `SECRET_KEY` and the database password are generated by Terraform
itself and only ever land in `.env` on the instance.

The application starts with `FILE_STORAGE_BACKEND=s3`, so uploaded files go into
the bucket immediately. To check: upload a file in `/files/` and look at
`aws s3 ls s3://your-bucket/filemanager/`.

If you deploy without Terraform, the least-privilege IAM policy is in
`deploy/aws/iam-policy.json` — put your bucket name into it.

### Tearing it all down afterwards

```bash
cd deploy/aws
terraform destroy   -var region=us-east-1   -var bucket_name=your-globally-unique-bucket   -var key_name=your-key-pair-name   -var image=ghcr.io/senpai520120/django-application-e2e:sha-75b13e9
```

One command removes the instance, the bucket together with its files
(`force_destroy = true`), the IAM role, the policy and the security group. A
manual check that nothing keeps charging:

- [ ] EC2 → Instances: the `users-and-roles-app` instance is terminated;
- [ ] S3 → the bucket is not in the list;
- [ ] IAM → Roles: no `users-and-roles-app` role;
- [ ] EC2 → Security Groups: no `users-and-roles-app` group;
- [ ] EC2 → Elastic IPs: no dangling addresses (Terraform creates none, but
      release any you allocated by hand — they cost money while idle);
- [ ] Billing → Cost Explorer a day later: zero for the project.

## Checking that passwords are hashed

```bash
# SQLite
python manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.values_list('username', 'password')[:5])"

# PostgreSQL
psql "$DATABASE_URL" -c "select username, password from auth_user limit 5;"
```

The `password` column must hold something shaped like
`pbkdf2_sha256$1000000$<salt>$<hash>`. The same thing is asserted by
`tests/test_auth.py::test_password_is_stored_hashed`.

## Layout

```
config/           settings, root urls.py, wsgi/asgi
accounts/         authentication, home page, access rules, role seeding
  permissions.py    is_admin() and the role names
  mixins.py         AdminRequiredMixin
  migrations/       data migration with the admin and user roles
  management/       the seed_groups command
panel/            the custom admin at /manage/
  views.py          lists, the roles form, user creation, the audit log
  forms.py          forms on top of the built-in ones
  models.py         RoleChange (the audit log)
files/            the file manager at /files/
  paths.py          path normalisation, protection from traversal
  storage.py        the storage contract plus local and s3
  access.py         who gets into the section
  views.py          listing, upload, rename, delete, download
e2e/              pytest + Playwright: scenarios in a browser
deploy/aws/       Terraform: S3, IAM role, EC2
templates/        base.html, registration/login.html, the panel, 403/404/500
static/css/       the single css file
tests/            pytest-django
```

## Known limitations

* The audit log covers role changes only. Creating a user and switching one on
  or off are not written into `RoleChange`: the model is shaped around roles. To
  log everything it would have to be generalised into an `AuditEntry` with an
  `action` field.
* There is no protection against password guessing. The login form does not
  limit attempts — a production project would put `django-axes` here, or a rate
  limit at the nginx level.
* `is_admin()` treats both a member of the `admin` group and anyone with
  `is_staff` as an admin. `is_staff` cannot be removed through the panel, only
  through `/admin/` or a shell; in the user list such flags are shown in a
  column of their own.
* There is no custom 400 page. 403, 404 and 500 have templates, so a rejected
  path shows Django's plain `Bad Request (400)` in production.
* The AWS stand served plain HTTP on port 80, so the sign-in form sent the
  password unencrypted. That was acceptable for a short demo with demo
  accounts only. In production TLS would come first (an ALB with an ACM
  certificate, or Caddy with Let's Encrypt in front of gunicorn), followed by
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` and HSTS,
  which CI already checks with `check --deploy`.
* The total size limit is counted on every upload by walking the whole storage
  (`rglob` on disk, a listing of every key in S3). That is fine for a team's
  share. With many thousands of files the total would be kept in the database
  and updated on save and delete instead.

## What was left out

Outside the scope of the assignment:

* user registration through a public UI — accounts are created by an admin or by
  `createsuperuser`;
* password recovery and email confirmation;
* a REST API, an SPA, JS frameworks;
* a separate `Role` model — a role is an `auth.Group`, and duplicating it buys
  nothing (should a role need a description, we would add `Role` with a
  `OneToOne` to `Group`).

SSO was outside the first assignment too; it was added later on request, see
"Sign-in through Keycloak (SSO)".

Django's stock `/admin/` is enabled, but the assignment is solved by our own
`/manage/` page.
