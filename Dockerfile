FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
# Static files are part of the image; DEBUG only lets settings load without the production secret.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput && useradd --create-home app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60 --access-logfile -"]
