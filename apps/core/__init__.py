

from django.conf import settings
from django.apps import AppConfig

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        import apps.core.signals  # noqa

        

        
