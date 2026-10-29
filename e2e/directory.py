"""People in the test Active Directory (Samba, docker-compose.ad.yml).

The tests play the domain's administrator here: they add a person, switch
them off or set a new password straight in AD, as IT would, and then check
what the app does. Keycloak only reads AD, so this is the only way to do it.
"""

import ssl

from ldap3 import MODIFY_REPLACE, Connection, Server, Tls

import config

# userAccountControl flags: an ordinary account, switched off, never expires.
NORMAL_ACCOUNT = 0x200
ACCOUNT_DISABLED = 0x2
PASSWORD_NEVER_EXPIRES = 0x10000


def _connection() -> Connection:
    # The test domain controller on this machine, with a certificate it made
    # for itself on its first start. Keycloak does check it (it trusts that
    # very certificate); this helper is only a test's hand on the directory.
    server = Server(config.AD_URL, use_ssl=True, tls=Tls(validate=ssl.CERT_NONE))
    return Connection(
        server,
        user=config.AD_ADMIN,
        password=config.AD_ADMIN_PASSWORD,
        auto_bind=True,
        raise_exceptions=True,
    )


def _dn(username: str) -> str:
    return f"CN={username},{config.AD_USERS_DN}"


def _password(value: str) -> bytes:
    # AD takes a new password as the quoted string in UTF-16, and only over TLS.
    return f'"{value}"'.encode("utf-16-le")


def add_person(username: str, password: str, email: str = "") -> None:
    """A new person in AD, able to sign in at once."""
    attributes = {
        "sAMAccountName": username,
        "userPrincipalName": f"{username}@{config.AD_EMAIL_DOMAIN}",
        "givenName": "Test",
        "sn": username,
        "unicodePwd": _password(password),
        "userAccountControl": NORMAL_ACCOUNT | PASSWORD_NEVER_EXPIRES,
    }
    if email:
        attributes["mail"] = email
    with _connection() as connection:
        connection.add(
            _dn(username),
            ["top", "person", "organizationalPerson", "user"],
            attributes,
        )


def switch_off(username: str) -> None:
    flags = NORMAL_ACCOUNT | ACCOUNT_DISABLED | PASSWORD_NEVER_EXPIRES
    with _connection() as connection:
        connection.modify(
            _dn(username), {"userAccountControl": [(MODIFY_REPLACE, [flags])]}
        )


def set_password(username: str, password: str) -> None:
    """The administrator's password reset, as in "Active Directory Users"."""
    with _connection() as connection:
        connection.modify(
            _dn(username), {"unicodePwd": [(MODIFY_REPLACE, [_password(password)])]}
        )


def remove(username: str) -> None:
    with _connection() as connection:
        connection.delete(_dn(username))
