#!/usr/bin/env bash
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Adjust appuser GID if needed
if [[ "${PGID}" != "1000" ]]; then
    if getent group "${PGID}" > /dev/null 2>&1; then
        printf "WARNING: GID %s is already in use, skipping groupmod\n" "${PGID}" >&2
    else
        groupmod -o -g "${PGID}" appuser
    fi
fi

# Adjust appuser UID if needed
if [[ "${PUID}" != "1000" ]]; then
    if getent passwd "${PUID}" > /dev/null 2>&1; then
        printf "WARNING: UID %s is already in use, skipping usermod\n" "${PUID}" >&2
    else
        usermod -o -u "${PUID}" appuser
    fi
fi

# Set ownership of app directory (non-recursive to avoid touching bind mounts)
chown "${PUID}:${PGID}" /app

# Drop privileges and start the app. The vweb entry point reads VWEB_HOST,
# VWEB_PORT, VWEB_WORKERS, and VWEB_ACCESS_LOG from the environment and
# dispatches to gunicorn when VWEB_DEBUG is false.
exec gosu appuser vweb
