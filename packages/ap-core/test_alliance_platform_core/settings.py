import hashlib
import os
from pathlib import Path
import random
from typing import TypedDict
import warnings

from alliance_platform.core.settings import AlliancePlatformCoreSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR

STATIC_URL = "/static/"


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType


ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "alliance_platform_core",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", None),
    }
}

INSTALLED_APPS = (
    "allianceutils",
    "test_alliance_platform_core",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rules.apps.AutodiscoverRulesConfig",
)

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "rules.permissions.ObjectPermissionBackend",
]

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

# -------------------------------------
# Custom settings
QUERY_COUNT_WARNING_THRESHOLD = 40

warnings.simplefilter("always")

try:
    from django.utils.deprecation import RemovedInDjango51Warning  # noqa
except ImportError:
    pass
else:
    # SHA1Passwordhasher might be on its way out but it is still good for test cases because it's
    # much faster than the (secure) alternatives
    warnings.filterwarnings(
        "ignore",
        category=PendingDeprecationWarning,
        message="django.contrib.auth.hashers.SHA1PasswordHasher is deprecated.",
    )
