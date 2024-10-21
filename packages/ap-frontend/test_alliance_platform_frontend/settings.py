import hashlib
import os
from pathlib import Path
import random
import re
from typing import TypedDict

from alliance_platform.codegen.settings import AlliancePlatformCodegenSettingsType
from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from alliance_platform.frontend.bundler.asset_registry import FrontendAssetRegistry
from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR
TEST_DIRECTORY = PROJECT_DIR / "test_alliance_platform_frontend"

STATIC_URL = "/static/"


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType
    FRONTEND: AlliancePlatformFrontendSettingsType
    CODEGEN: AlliancePlatformCodegenSettingsType


frontend_registry = FrontendAssetRegistry()

ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
    "CODEGEN": {},
    "FRONTEND": {
        "FRONTEND_ASSET_REGISTRY": frontend_registry,
        "REACT_RENDER_COMPONENT_FILE": PROJECT_DIR / "frontend/src/renderComponent.tsx",
        "PRODUCTION_DIR": TEST_DIRECTORY / "frontend/build",
        "DEBUG_COMPONENT_OUTPUT": True,
        "BUNDLER": "test_alliance_platform_frontend.bundler.vite_bundler",
        "EXTRACT_ASSETS_EXCLUDE_DIRS": (
            TEST_DIRECTORY / "codegen",
            re.compile(r".*/site-packages/.*"),
        ),
        "BUNDLER_DISABLE_DEV_CHECK_HTML": False,
        "SSR_GLOBAL_CONTEXT_RESOLVER": None,
        "NODE_MODULES_DIR": os.environ.get("NODE_MODULES_DIR", BASE_DIR.parent.parent / "node_modules"),
    },
}

VITE_BUNDLER_MODE = "development"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "alliance_platform_frontend",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", None),
    }
}

INSTALLED_APPS = (
    "allianceutils",
    "alliance_platform.frontend",
    "test_alliance_platform_frontend",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rules.apps.AutodiscoverRulesConfig",
)

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "rules.permissions.ObjectPermissionBackend",
]

AUTH_USER_MODEL = "test_alliance_platform_frontend.User"

MIDDLEWARE = (
    "django.middleware.security.SecurityMiddleware",  # various security, ssl settings (django >=1.9)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware",
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

# ROOT_URLCONF = "test_alliance_platform_frontend.urls"

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
