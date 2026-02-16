from .settings import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "agent-commons-tests",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MIGRATION_MODULES = {
    "core": None,
    "api": None,
    "pages": None,
    "docs": None,
}

Q_CLUSTER = {
    "sync": True,
}
