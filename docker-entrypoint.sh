#!/bin/sh
set -e

# Wait for PostgreSQL database if DB_HOST is configured
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
  python -c "
import socket, time, os, sys
host = os.getenv('DB_HOST')
port = int(os.getenv('DB_PORT', '5432'))
start = time.time()
while time.time() - start < 60:
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f'Successfully connected to database at {host}:{port}')
        sys.exit(0)
    except OSError:
        time.sleep(2)
print('Warning: Database connection timed out after 60s, continuing anyway...')
"
fi

# Run database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files for production serving via Whitenoise
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Provision superuser if credentials are provided
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Ensuring superuser '$DJANGO_SUPERUSER_USERNAME' exists..."
  python manage.py createsuperuser --noinput 2>/dev/null || true
fi

# Execute CMD passed to container, or fallback to production Gunicorn
if [ $# -eq 0 ]; then
  PORT="${PORT:-8000}"
  WORKERS="${GUNICORN_WORKERS:-3}"
  TIMEOUT="${GUNICORN_TIMEOUT:-120}"
  echo "Starting Gunicorn on 0.0.0.0:${PORT} with ${WORKERS} workers..."
  exec gunicorn Core.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile -
else
  echo "Executing custom command: $@"
  exec "$@"
fi
