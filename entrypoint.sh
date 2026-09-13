#!/bin/sh
set -e

echo "=== Starting SIH26002 Backend Container ==="

# Wait for database if DB_HOST is set and not sqlite
if [ "$USE_SQLITE" != "True" ] && [ "$USE_SQLITE" != "true" ] && [ "$USE_SQLITE" != "1" ]; then
    if [ -n "$DB_HOST" ]; then
        echo "Waiting for PostgreSQL database at $DB_HOST:${DB_PORT:-5432}..."
        while ! nc -z "$DB_HOST" "${DB_PORT:-5432}" >/dev/null 2>&1; do
            sleep 1
        done
        echo "Database is reachable."
    fi
fi

# Apply database migrations if running web service
if [ "$1" = "python" ] && [ "$2" = "manage.py" ] && [ "$3" = "runserver" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput || echo "Migrations skipped or encountered an error"
    
    echo "Collecting static files..."
    python manage.py collectstatic --noinput || echo "Static collection completed"
elif [ "$1" = "gunicorn" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput || echo "Migrations skipped or encountered an error"
    
    echo "Collecting static files..."
    python manage.py collectstatic --noinput || echo "Static collection completed"
fi

echo "Executing command: $@"
exec "$@"
