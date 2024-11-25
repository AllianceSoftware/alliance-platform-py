from datetime import datetime
import hashlib
import re
from typing import TYPE_CHECKING
from typing import Optional

from django.apps import apps
from django.db import models
from django.db.models.fields.related_descriptors import ManyToManyDescriptor


def is_m2m(source_model, fieldname):
    return isinstance(getattr(source_model, fieldname, None), ManyToManyDescriptor)


def _get_name_from_label(label: str, action: str) -> str:
    """
    Given a history event label, generate a trigger name.
    Also tries to respect 43char rule (trigger names cant be longer than 43)
    """
    if len(label) + len(action) >= 43 - 1:
        if len(action) >= 20:
            raise ValueError(
                f"Audit: failed to generate the label. Action should be fewer than 20 chars, got {len(action)}: {action}"
            )
        max_label_len = 43 - 1 - len(action) - 8
        hash = hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
        label = label[:max_label_len] + hash
    label = f"{label}_{action}"
    return re.sub("[^0-9a-zA-Z]+", "_", label)


def get_model_module(model: type[models.Model]) -> str:
    # because we're constructing the model dynamically we need to let django know which
    # app it's supposed to be part of which we do by manually setting the module
    app = apps.app_configs[model._meta.app_label]
    models_module = getattr(app.module, "__name__") + ".models"
    return models_module


if TYPE_CHECKING:

    class AuditEventProtocol(models.Model):
        pgh_tracked_model: type[models.Model]
        pgh_label: str
        pgh_previous: Optional[type[models.Model]]
        pgh_created_at: datetime
        registration_hash: str
        model_label: Optional[str]

else:

    class AuditEventProtocol:
        pass
