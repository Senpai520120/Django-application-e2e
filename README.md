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
| Tests | pytest + pytest-django, 157 tests, 95% coverage |
| Lint | ruff + black, run by hand and in CI |
| E2E | Playwright (chromium), panel and file manager scenarios |
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
| `e2e/` | Playwright: panel and file manager scenarios in a browser |
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

The backend is chosen by `get_storage()` from `FILE_STORAGE_BACKEND`, which also
sets `STORAGES["default"]` in the settings — the same way `DATABASE_URL` picks a
database. A third backend is added as a new subclass: views and templates stay
as they are.

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
without a cloud, use localstack:

```bash
docker compose --profile s3 up --build
# additionally in .env: AWS_S3_ENDPOINT_URL=http://localstack:4566
```

### Security

| What | How it is closed |
| --- | --- |
| Path traversal | `files/paths.py`: `..`, absolute paths, drive letters and null bytes are rejected before the storage is touched, and the answer is 400 |
| Symlink leading out | the local storage additionally compares the already resolved path with the root |
| File names | separators, control characters and names reserved by Windows are forbidden, and length is capped at 120 characters |
| Size | a per-file limit and a total-storage limit, both from the environment |
| Dangerous extensions | a download always carries `Content-Disposition: attachment` plus `X-Content-Type-Options: nosniff`, so the browser never executes an `.html` or an `.svg` |
| Overwriting | a file with an existing name is not silently overwritten but answered with an error |
| Secrets | AWS keys live only in `.env` and in the IAM role; the repository holds none |

Every line above is covered by tests: `tests/test_files_paths.py`,
`tests/test_files_storage.py`, `tests/test_files_views.py`.

## Tests

```bash
pytest                                  # 157 tests
pytest -v
pytest --cov --cov-report=term-missing  # coverage (95% right now)
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
  header on download, recursive deletion, and 400 on a path leading outside.

The test environment lives in `config/settings_test.py`; the user fixtures are in
`tests/conftest.py`.

## E2E tests (Playwright)

Pytest checks the backend and the views; Playwright checks that the scenario
works in a real browser. Neither replaces the other.

```bash
cd e2e
npm ci
npx playwright install chromium
BASE_URL=http://127.0.0.1:8000 npx playwright test      # against a running stack
npx playwright show-report                              # the report afterwards
```

The app under test is started by the same `docker compose` as usual. The account
comes from `seed_demo_users` — `demo_admin` with the password above, overridable
through `E2E_USERNAME` / `E2E_PASSWORD`.

Run Playwright **from the `e2e/` directory**. There is no config in the
repository root, so from there the runner and the specs end up with two
different instances of `@playwright/test` and every file fails with "did not
expect test.describe() to be called here". Use `--config e2e/playwright.config.ts`
if you have to launch it from elsewhere.

```
e2e/
├── playwright.config.ts   baseURL from the environment, retries in CI only,
│                          trace on-first-retry, video and screenshot on failure
├── support/
│   ├── fixtures.ts        login, unique names, the panel and workspace fixtures
│   ├── panel.page.ts      Page Object of the admin panel
│   └── file-manager.page.ts   Page Object of the files section
├── auth.spec.ts           anonymous access, sign-in, moving into the section,
│                          the identical answer to a wrong password and an
│                          unknown login
├── panel.spec.ts          granting and revoking a role, cancelling the form,
│                          the ban on stripping admin from yourself,
│                          deactivation, the audit record, the counter on the
│                          Roles page, creating a user, a weak password
├── folders.spec.ts        creation, nesting, breadcrumbs, duplicates, deletion
└── files.spec.ts          upload (one and several), rename, download, delete,
                           a file over the limit
```

Every file test works in a folder of its own with a unique name and cleans it up
afterwards; the panel tests return the demo user to the original set of roles in
`afterEach` and create new users under unique names. Runs depend neither on each
other nor on order. There are no timer-based waits: only web-first assertions,
which wait for the state they need on their own.

**About codegen.** Scenario drafts were recorded with `npx playwright codegen`
and then put in order by hand: locators were replaced with `getByRole`,
`getByLabel` and `getByTestId`, repeated steps were moved into Page Objects and
fixtures, and the steps were labelled with `test.step()`. For stable locators a
few `aria-label`, `role="status"` and `data-testid` attributes were added to the
templates on purpose — that is more honest than clinging to markup classes.

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
| **E2E (Playwright)** | starts the same stack, installs chromium, runs the panel and file manager scenarios, and on failure keeps the Playwright report as an artifact |
| **Publish to GHCR** | waits for a green smoke and E2E; for `main` and `v*` tags only: builds the image and pushes it to `ghcr.io/<owner>/<repo>` with the `latest`, `sha-…` and semver tags. Uses the built-in `GITHUB_TOKEN`, so no secrets to configure |

CD goes as far as publishing the image: after that, `docker compose pull &&
docker compose up -d` with that image is enough on your own server. Dependency
updates come from `.github/dependabot.yml` (pip, npm, GitHub Actions, Docker and
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
| Instance IAM role | access to the bucket limited to `ListBucket`, `GetObject`, `PutObject`, `DeleteObject` — no keys in the code and no `AdministratorAccess` |
| Security group | only port 80 is open outward; SSH only if you name your own address |

```
browser → EC2 (:80 → gunicorn:8000) ─┬→ Postgres in a container on the same instance
                                     └→ S3 (files), reached by IAM role, IMDSv2
```

### The live stand

It was deployed and verified end to end — the application worked and files went
into S3 — and then torn down, so the address below no longer answers. It is kept
here as a record of what was checked.

| | |
| --- | --- |
| Address | http://100.54.108.163/ (decommissioned) |
| Account for a look around | `demo_admin` / `demo-password-123` |
| Region | `us-east-1` |
| Bucket | `users-and-roles-files-f92fa1c9` |
| Image | `ghcr.io/senpai520120/django_application:0.2.0` |

### Steps

```bash
cd deploy/aws
terraform init
terraform apply   -var region=us-east-1   -var bucket_name=your-globally-unique-bucket   -var key_name=your-key-pair-name   -var ssh_cidr=your.ip.address/32   -var image=ghcr.io/senpai520120/django_application:0.2.0
```

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
terraform destroy   -var region=us-east-1   -var bucket_name=users-and-roles-files-f92fa1c9   -var key_name=test_django
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
e2e/              Playwright: scenarios in a browser
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

## What was left out

Outside the scope of the assignment:

* user registration through a public UI — accounts are created by an admin or by
  `createsuperuser`;
* password recovery, email confirmation, OAuth/SSO;
* a REST API, an SPA, JS frameworks;
* a separate `Role` model — a role is an `auth.Group`, and duplicating it buys
  nothing (should a role need a description, we would add `Role` with a
  `OneToOne` to `Group`).

Django's stock `/admin/` is enabled, but the assignment is solved by our own
`/manage/` page.
