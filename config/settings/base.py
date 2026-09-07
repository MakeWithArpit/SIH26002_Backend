import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'default-unsafe-secret-key-change-me')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
]

LOCAL_APPS = [
    'apps.accounts.apps.AccountsConfig',
    'apps.common',
    'apps.intelligence.apps.IntelligenceConfig',
    'apps.reports.apps.ReportsConfig',
    'apps.routes.apps.RoutesConfig',
    'apps.vehicles.apps.VehiclesConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# GeoDjango / GDAL library paths (needed on Windows when PostGIS is enabled)
if os.name == 'nt':
    pg_bin = Path(os.getenv('POSTGRES_BIN_PATH', r'C:\Program Files\PostgreSQL\18\bin'))
    if pg_bin.exists():
        try:
            os.add_dll_directory(str(pg_bin))
        except (AttributeError, OSError):
            pass
        os.environ['PATH'] = str(pg_bin) + ';' + os.environ.get('PATH', '')
        gdal_dll = next(pg_bin.glob('*gdal*.dll'), None)
        geos_dll = pg_bin / 'libgeos_c.dll'
        if gdal_dll and gdal_dll.exists():
            GDAL_LIBRARY_PATH = str(gdal_dll)
        if geos_dll.exists():
            GEOS_LIBRARY_PATH = str(geos_dll)

# Database Configuration
USE_SQLITE = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 't')

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    db_engine = os.getenv('DB_ENGINE', 'django.contrib.gis.db.backends.postgis')
    DATABASES = {
        'default': {
            'ENGINE': db_engine,
            'NAME': os.getenv('DB_NAME', 'sih26002_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.common.exceptions.custom_exception_handler',
}

# SimpleJWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# Spectacular API Docs
SPECTACULAR_SETTINGS = {
    'TITLE': 'SIH26002 Backend API',
    'DESCRIPTION': 'AI-Based Smart Logistics and Accessibility Intelligence Platform API',
    'VERSION': 'v1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173'
    ).split(',')
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# CSRF Trusted Origins (Required for Cloudflare Tunnel, Ngrok, and Remote Access)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:8000,http://127.0.0.1:8000,https://*.trycloudflare.com'
    ).split(',')
    if origin.strip()
]

# Reverse Proxy / Cloudflare Tunnel SSL Header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True


# Geospatial / Landslide Static Enrichment Configuration
# Note: The 500m proximity threshold is an MVP configuration parameter, not a scientifically validated risk threshold.
LANDSLIDE_PROXIMITY_THRESHOLD_M = float(os.getenv('LANDSLIDE_PROXIMITY_THRESHOLD_M', 500.0))
LANDSLIDE_METRIC_SRID = int(os.getenv('LANDSLIDE_METRIC_SRID', 32646))
LANDSLIDE_INVENTORY_PATH = BASE_DIR / os.getenv(
    'LANDSLIDE_INVENTORY_PATH', 'data/geospatial/gsi/landslide_inventory.geojson'
)
LANDSLIDE_SUSCEPTIBILITY_PATH = BASE_DIR / os.getenv(
    'LANDSLIDE_SUSCEPTIBILITY_PATH', 'data/geospatial/gsi/landslide_susceptibility_demo.geojson'
)

# Weather Intelligence Configuration
WEATHER_PROVIDER = os.getenv('WEATHER_PROVIDER', 'open_meteo')
OPEN_METEO_BASE_URL = os.getenv('OPEN_METEO_BASE_URL', 'https://api.open-meteo.com/v1/forecast')
OPEN_METEO_TIMEOUT_SECONDS = float(os.getenv('OPEN_METEO_TIMEOUT_SECONDS', 10.0))
WEATHER_RECENT_RAINFALL_HOURS = int(os.getenv('WEATHER_RECENT_RAINFALL_HOURS', 24))

# Celery & Redis Configuration (Optional / Non-blocking)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Infrastructure Risk Engine Configuration (apps.intelligence)
RISK_WEIGHT_LANDSLIDE_SUSCEPTIBILITY_HIGH = float(os.getenv('RISK_WEIGHT_LANDSLIDE_SUSCEPTIBILITY_HIGH', 30.0))
RISK_WEIGHT_HISTORICAL_LANDSLIDE = float(os.getenv('RISK_WEIGHT_HISTORICAL_LANDSLIDE', 15.0))
RISK_WEIGHT_FLOOD_HAZARD = float(os.getenv('RISK_WEIGHT_FLOOD_HAZARD', 15.0))
RISK_WEIGHT_HEAVY_RAINFALL = float(os.getenv('RISK_WEIGHT_HEAVY_RAINFALL', 25.0))
RISK_WEIGHT_WEATHER_WARNING = float(os.getenv('RISK_WEIGHT_WEATHER_WARNING', 10.0))

RISK_RAINFALL_MIN_MM = float(os.getenv('RISK_RAINFALL_MIN_MM', 20.0))
RISK_RAINFALL_MAX_MM = float(os.getenv('RISK_RAINFALL_MAX_MM', 50.0))

RISK_THRESHOLD_LOW_MAX = float(os.getenv('RISK_THRESHOLD_LOW_MAX', 39.0))
RISK_THRESHOLD_MEDIUM_MAX = float(os.getenv('RISK_THRESHOLD_MEDIUM_MAX', 69.0))

# Route Optimization Engine Configuration (apps.intelligence)
OPTIMIZATION_DISTANCE_WEIGHT = float(os.getenv('OPTIMIZATION_DISTANCE_WEIGHT', 0.60))
OPTIMIZATION_RISK_WEIGHT = float(os.getenv('OPTIMIZATION_RISK_WEIGHT', 0.40))


