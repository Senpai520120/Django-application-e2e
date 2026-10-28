# Samba as an Active Directory domain controller, for development and tests.
# Keycloak reads the directory over LDAPS; nothing else talks to it.
FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        samba samba-ad-dc samba-ad-provision winbind ldb-tools openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/samba/smb.conf

COPY entrypoint.sh /usr/local/bin/samba-entrypoint.sh
RUN chmod +x /usr/local/bin/samba-entrypoint.sh

EXPOSE 636
ENTRYPOINT ["/usr/local/bin/samba-entrypoint.sh"]
