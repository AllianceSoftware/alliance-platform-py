import hashlib
import re

from django.db.models import Model


def generate_model_trigger_name(model: type[Model], suffix: str) -> str:
    """
    Given a model, generate a trigger name.

    Trigger names can't be longer than 43 characters so will enforce this. If suffix is too long
    to accommodate the model label then the model label will be hashed and 8 characters of that will
    be used as a prefix to ensure uniqueness.

    If suffix is too long still an error will be thrown

    Args:
        model: The model to generate a name for
        suffix: Suffix string to add to the label generated from the model.
    """
    label = f"{model._meta.app_label}.{model._meta.object_name}_"
    hash_length = 8
    max_trigger_length = 43
    max_suffix_length = max_trigger_length - hash_length
    if len(suffix) > max_suffix_length:
        raise ValueError(f"suffix {suffix} is too long; must be at most {max_suffix_length}")
    if len(label) + len(suffix) >= max_trigger_length:
        max_label_len = max_trigger_length - len(suffix) - hash_length
        hash = hashlib.sha256(label.encode("utf-8")).hexdigest()[:hash_length]
        label = label[:max_label_len] + hash
    label = f"{label}{suffix}"
    return re.sub("[^0-9a-zA-Z]+", "_", label).lower()
