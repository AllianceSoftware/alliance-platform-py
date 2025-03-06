import hashlib
import os
from pathlib import Path
import random
from typing import TypedDict

from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from alliance_platform.frontend.bundler.asset_registry import FrontendAssetRegistry
from alliance_platform.server_choices.settings import AlliancePlatformServerChoicesSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR
TEST_DIRECTORY = PROJECT_DIR / "test_alliance_platform_server_choices"

STATIC_URL = "/static/"

ROOT_URLCONF = "test_alliance_platform_server_choices.urls"

MEDIA_ROOT = os.path.join(os.path.dirname(__file__), "static_files")
MEDIA_URL = "/custom-media/"
STATICFILES_DIRS = [MEDIA_ROOT]

AUTH_USER_MODEL = "test_alliance_platform_server_choices.User"


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType
    SERVER_CHOICES: AlliancePlatformServerChoicesSettingsType


frontend_registry = FrontendAssetRegistry()

ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
    "SERVER_CHOICES": {},
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_alliance_platform_server_choices",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", None),
    }
}

INSTALLED_APPS = (
    "allianceutils",
    "alliance_platform.server_choices",
    "test_alliance_platform_server_choices",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
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

# -------------------------------------
# Test case performance
PASSWORD_HASHERS = (
    #'django_plainpasswordhasher.PlainPasswordHasher', # very fast but extremely insecure
    "django.contrib.auth.hashers.SHA1PasswordHasher",  # fast but insecure
)
