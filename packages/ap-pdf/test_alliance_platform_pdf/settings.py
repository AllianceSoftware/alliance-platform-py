import hashlib
import os
from pathlib import Path
import random
from typing import TypedDict

from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from alliance_platform.pdf.settings import AlliancePlatformPDFSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"
BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR
STATIC_URL = "/static/"


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType
    PDF: AlliancePlatformPDFSettingsType


ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
    "PDF": {},
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "alliance_platform_pdf",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", None),
    }
}
INSTALLED_APPS = (
    "allianceutils",
    "alliance_platform.pdf",
    "test_alliance_platform_pdf",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rules.apps.AutodiscoverRulesConfig",
)
MIDDLEWARE = (
    "django.middleware.security.SecurityMiddleware",  # various security, ssl settings (django >=1.9)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
)
TEMPLATE_DIRS = (
    # os.path.join(BASE_DIR, 'compat/tests/templates/')
)
TEMPLATES = (
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "DIRS": TEMPLATE_DIRS,
    },
)
STATIC_ROOT = Path(BASE_DIR, "static")
SERIALIZATION_MODULES = {
    "json_ordered": "allianceutils.serializers.json_ordered",
}
SECRET_KEY = hashlib.sha256(str(random.SystemRandom().getrandbits(256)).encode("ascii")).hexdigest()
USE_TZ = True
TIME_ZONE = "Australia/Melbourne"
# -------------------------------------
# Test case performance
PASSWORD_HASHERS = (
    #'django_plainpasswordhasher.PlainPasswordHasher', # very fast but extremely insecure
    "django.contrib.auth.hashers.SHA1PasswordHasher",  # fast but insecure
)
