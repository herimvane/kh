#!/bin/sh
set -eu

if [ -n "${INITIAL_ADMIN_PASSWORD_FILE:-}" ]; then
    if [ ! -r "$INITIAL_ADMIN_PASSWORD_FILE" ]; then
        echo "Cannot read INITIAL_ADMIN_PASSWORD_FILE: $INITIAL_ADMIN_PASSWORD_FILE" >&2
        exit 1
    fi
    INITIAL_ADMIN_PASSWORD="$(cat "$INITIAL_ADMIN_PASSWORD_FILE")"
    export INITIAL_ADMIN_PASSWORD
fi

initialize_database() {
    if [ -n "${INITIAL_ADMIN_PASSWORD:-}" ]; then
        python scripts/init_database.py \
            --admin-username "${INITIAL_ADMIN_USERNAME:-admin}" \
            --admin-name "${INITIAL_ADMIN_NAME:-系统管理员}" \
            --preserve-existing-admin
    else
        python scripts/init_database.py --skip-admin
    fi
}

attempt=1
max_attempts="${DB_INIT_MAX_ATTEMPTS:-30}"
until initialize_database; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Database initialization failed after $attempt attempts." >&2
        exit 1
    fi
    echo "Database is not ready; retrying in 2 seconds ($attempt/$max_attempts)." >&2
    attempt=$((attempt + 1))
    sleep 2
done

exec "$@"
