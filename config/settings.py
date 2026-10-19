import os
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-change-me")
if not DEBUG and SECRET_KEY in ("development-only-change-me", "replace-with-a-long-random-value"):
    raise RuntimeError("DJANGO_SECRET_KEY must be set for production")
ALLOWED_HOSTS = [x.strip() for x in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "board",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "board.middleware.content_security_policy",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.debug", "django.template.context_processors.request", "django.template.context_processors.i18n", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages", "board.views.public_base", "board.views.languages", "board.candidate_mail.candidate_navigation"]}}]
WSGI_APPLICATION = "config.wsgi.application"
database_url = os.environ.get("DATABASE_URL")
if database_url:
    db = urlparse(database_url)
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": db.path.lstrip("/"), "USER": unquote(db.username or ""), "PASSWORD": unquote(db.password or ""), "HOST": db.hostname, "PORT": db.port or 5432, "CONN_HEALTH_CHECKS": True}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LOGIN_URL = "candidate_login"
LOGIN_REDIRECT_URL = "candidate_profile"
LOGOUT_REDIRECT_URL = "jobs"
# Account flows can be built and tested while all production delivery remains off.
CANDIDATE_MAIL_ENABLED = os.environ.get("CANDIDATE_MAIL_ENABLED", "0") == "1"
CANDIDATE_SIGNUP_ENABLED = os.environ.get("CANDIDATE_SIGNUP_ENABLED", "0") == "1"
JOB_ALERTS_ENABLED = os.environ.get("JOB_ALERTS_ENABLED", "0") == "1"
JOB_ALERTS_ACTIVE_SINCE = os.environ.get("JOB_ALERTS_ACTIVE_SINCE", "")
EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "")
CANDIDATE_OPERATOR_NAME = os.environ.get("CANDIDATE_OPERATOR_NAME", "")
CANDIDATE_PRIVACY_EMAIL = os.environ.get("CANDIDATE_PRIVACY_EMAIL", "")
CANDIDATE_EMAIL_PROCESSOR = os.environ.get("CANDIDATE_EMAIL_PROCESSOR", "")
LANGUAGE_CODE = "bs"
TIME_ZONE = "Europe/Sarajevo"
USE_I18N = True
# Bosnian is served without a prefix, English under /en/. Admin, feed and health URLs are not prefixed and stay Bosnian.
LANGUAGES = [("bs", "Bosanski"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
# HTTPS is terminated at the reverse proxy. Both are opt-in: the container healthcheck calls plain http://127.0.0.1:8000/health/, and HSTS cannot be withdrawn once browsers cache it.
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
SECURE_REDIRECT_EXEMPT = [r"^health/"]
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
# Compose collects stdout and stderr; errors must reach its logs even with DEBUG off.
# Public links (canonical, sitemap, robots) use this origin when set, so they do not depend on proxy Host headers.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"console": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "console"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "WARNING"), "propagate": False},
        "board": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
