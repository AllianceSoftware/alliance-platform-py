import hashlib
import os
from pathlib import Path
import random
import re
from typing import TypedDict

from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from alliance_platform.frontend.bundler.asset_registry import FrontendAssetRegistry
from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType
from alliance_platform.pdf.settings import AlliancePlatformPDFSettingsType

is_ci = os.environ.get("CI_SERVER", "no") == "yes"

BASE_DIR = Path(__file__).parent.parent
PROJECT_DIR = BASE_DIR
TEST_DIRECTORY = PROJECT_DIR / "test_alliance_platform_pdf"

STATIC_URL = "/static/"

ROOT_URLCONF = "test_alliance_platform_pdf.urls"

MEDIA_ROOT = os.path.join(os.path.dirname(__file__), "static_files")
MEDIA_URL = "/custom-media/"
STATICFILES_DIRS = [MEDIA_ROOT]


class AlliancePlatformSettings(TypedDict):
    CORE: AlliancePlatformCoreSettingsType
    PDF: AlliancePlatformPDFSettingsType
    FRONTEND: AlliancePlatformFrontendSettingsType


frontend_registry = FrontendAssetRegistry()

ALLIANCE_PLATFORM: AlliancePlatformSettings = {
    "CORE": {
        "PROJECT_DIR": PROJECT_DIR,
    },
    "FRONTEND": {
        "FRONTEND_ASSET_REGISTRY": frontend_registry,
        "REACT_RENDER_COMPONENT_FILE": PROJECT_DIR / "frontend/src/renderComponent.tsx",
        "PRODUCTION_DIR": TEST_DIRECTORY / "frontend/build",
        "DEBUG_COMPONENT_OUTPUT": True,
        "BUNDLER": "test_alliance_platform_pdf.bundler.vite_bundler",
        "EXTRACT_ASSETS_EXCLUDE_DIRS": (
            TEST_DIRECTORY / "codegen",
            re.compile(r".*/site-packages/.*"),
        ),
        "BUNDLER_DISABLE_DEV_CHECK_HTML": False,
        "SSR_GLOBAL_CONTEXT_RESOLVER": None,
        "NODE_MODULES_DIR": os.environ.get("NODE_MODULES_DIR", BASE_DIR.parent.parent / "node_modules"),
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
