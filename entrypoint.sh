#!/bin/sh
set -e

echo "=== Starting SIH26002 Backend Container ==="

# Wait for database if DB_HOST is set and not sqlite
if [ "$USE_SQLITE" != "True" ] && [ "$USE_SQLITE" != "true" ] && [ "$USE_SQLITE" != "1" ]; then
    if [ -n "$DB_HOST" ]; then
        echo "Waiting for PostgreSQL database at $DB_HOST:${DB_PORT:-5432}..."
        timeout=30
        while ! nc -z "$DB_HOST" "${DB_PORT:-5432}" >/dev/null 2>&1; do
            timeout=$((timeout - 1))
            if [ "$timeout" -le 0 ]; then
                echo "Warning: Database check timed out at $DB_HOST:${DB_PORT:-5432}. Proceeding anyway..."
                break
            fi
            sleep 1
        done
        if [ "$timeout" -gt 0 ]; then
            echo "Database is reachable."
        fi
    fi
fi

# Apply database migrations if running web service
case "$*" in
    *runserver*|*gunicorn*)
        echo "Applying database migrations..."
        python manage.py migrate --noinput || echo "Migrations skipped or encountered an error"
        
        echo "Collecting static files..."
        python manage.py collectstatic --noinput || echo "Static collection completed"
        ;;
esac

echo "Executing command: $@"
exec "$@"
