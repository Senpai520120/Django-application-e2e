#!/bin/sh
# First start: make the domain and the test users. The container keeps no
# volume for the domain, so `down` and a rebuild start it afresh.
set -e

REALM="${SAMBA_REALM:-CORP.EXAMPLE.TEST}"
DOMAIN="${SAMBA_DOMAIN:-CORP}"
# Shared with Keycloak, which trusts the certificate. Kept in a volume and made
# once: Keycloak reads it only when it starts, so a new one on every start of
# Samba would leave a running Keycloak distrusting it.
TLS=/tls

if [ ! -f "$TLS/samba.pem" ]; then
    # Keycloak connects to ldaps://samba and checks the name in the certificate.
    echo "==> TLS certificate for samba"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=samba" -addext "subjectAltName=DNS:samba,DNS:localhost" \
        -keyout "$TLS/samba-key.pem" -out "$TLS/samba.pem" 2>/dev/null
fi
chmod 600 "$TLS/samba-key.pem"

if [ ! -f /var/lib/samba/private/sam.ldb ]; then
    echo "==> Provisioning $REALM"
    samba-tool domain provision \
        --realm="$REALM" --domain="$DOMAIN" \
        --server-role=dc --dns-backend=SAMBA_INTERNAL \
        --adminpass="$SAMBA_ADMIN_PASSWORD" \
        --option="tls enabled = yes" \
        --option="tls keyfile = $TLS/samba-key.pem" \
        --option="tls certfile = $TLS/samba.pem" \
        --option="tls cafile = " \
        --option="dns forwarder = 127.0.0.11" \
        --option="acl_xattr:security_acl_name = user.NTACL"
    # Without CAP_SYS_ADMIN the container cannot write security.* attributes;
    # acl_xattr keeps the sysvol ACLs in user.* ones instead.

    # AD lets the old password in for 60 minutes after a change, and Samba
    # does so for LDAP sign-in too; the tests want the change to bite at once.
    # (provision drops this option, so it goes into smb.conf by hand.)
    sed -i '/^\[global\]/a\	old password allowed period = 0' /etc/samba/smb.conf

    # Test users must not expire in the middle of a test run.
    samba-tool domain passwordsettings set --max-pwd-age=0 >/dev/null

    # The account Keycloak reads the directory with: CN=svc-keycloak,CN=Users,...
    samba-tool user create "$SAMBA_BIND_USER" "$SAMBA_BIND_PASSWORD" \
        --use-username-as-cn --given-name=Keycloak --surname=Reader
    samba-tool user setexpiry "$SAMBA_BIND_USER" --noexpiry

    # username  first  last  email
    while read -r name first last email; do
        [ -n "$name" ] || continue
        samba-tool user create "$name" "$SAMBA_USERS_PASSWORD" --use-username-as-cn \
            --given-name="$first" --surname="$last" --mail-address="$email"
        samba-tool user setexpiry "$name" --noexpiry
    done <<EOF
ad_alice Alice Adams ad_alice@corp.example.test
ad_bob Bob Brown ad_bob@corp.example.test
ad_disabled Dan Disabled ad_disabled@corp.example.test
EOF
    samba-tool user disable ad_disabled
fi

echo "==> Starting Samba AD DC"
exec samba --foreground --no-process-group
