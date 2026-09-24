FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

# Static files are collected at build time, not on every container start.
# SECRET_KEY here is a dummy: collectstatic never uses it, settings demand it.
RUN mkdir -p /app/filemanager \
    && SECRET_KEY=build-time-only DEBUG=False python manage.py collectstatic --noinput \
    && chmod +x /app/docker/entrypoint.sh \
    && useradd --create-home --uid 1000 app \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
