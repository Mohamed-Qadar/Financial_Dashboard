"""Settings for the test suite.

Tests connect as the owner role so pytest can create and migrate the test database. Code
under test that must run with the restricted runtime role switches to it explicitly
(see apps.core.testing.as_app_role).
"""

import os

os.environ.setdefault("DJANGO_DB_ROLE", "owner")

from config.settings import *  # noqa: F403
