from datetime import datetime
from typing import Any
from typing import cast

from alliance_platform.audit.registry import _registration_by_model
from django.db import models as _models
from pghistory.models import Context as _ContextModel


def search_audit_by_context(
    search: dict[str, Any],
    created_between: tuple[datetime | None, datetime | None] = (None, None),
    models: list[type[_models.Model]] | None = None,
) -> dict[type[_models.Model], type[_models.QuerySet]]:
    """
    Given `search` , returns all audit histories from all registered models with context matching
    the search dict.

    The search is partial: `{"user": 1}` will return all entries with context value containing
    `user=1` regardless of what other values may be set.

    A created_between can be passed in to restrict to only find contexts created between two datetime
    points; passing None in either of them resulted in the relevant side to be open ended.

    You can also pass in models to restrict what kind of source models the search should look for,
    by default it searches across all registered models.

    By default context is populated by `AuditMiddleware` and includes

    * **user** - the user (or hijacked user) who triggered the changed
    * **hijacker** - the original user in the case `user` is hijacked
    * **url** - the current URL
    * **ip** - the users IP address (only if ``TRACK_IP_ADDRESS` enabled)

    Extra context can be added with [pghistory.context](https://django-pghistory.readthedocs.io/en/latest/package.html#pghistory.context).

    For changes that occur outside of a request no context will be set unless explicitly wrapped in `pghistory.context`.

    Returns a dict indexed by models with values being the queryset, eg: `{PaymentRecord: qs}` where
    `qs` is a PaymentRecordAuditEvent queryset containing all hits, which can then be queried upon
    further depending on your need (eg, `qs.filter(payment_method="cash")`).
    WARNING: all searched models are returned in the dict regardless of whether their `qs.count() == 0`
    for performance reasons. Do not rely on keys of returned dict to direvtly decide which model contained
    a hit.

    usage:

    .. code-block:: python

        # find all changes made to Favorite and PaymentRecord models by user 2 hijacking someone else
        # on /payments/ url before yesterday, regardless of who this user impersonated as
        search_audit_by_context(
            search={
                'hijacker': 2,
                'url': '/payments/',
            },
            created_between=[None, timezone.now()+timedelta(days=-1)],
            models=[Favorite, PaymentRecord]
        )

    """
    search_param = {}
    for i, j in search.items():
        search_param["metadata__" + i] = j

    contexts_qs = _ContextModel.objects.all()
    if search_param:
        contexts_qs = contexts_qs.filter(**search_param)
    if created_between[0]:
        contexts_qs = contexts_qs.filter(created_at__gte=created_between[0])
    if created_between[1]:
        contexts_qs = contexts_qs.filter(created_at__lte=created_between[1])
    contexts = contexts_qs.values_list("id")

    models_to_search = []
    if not models:
        for m, reg in _registration_by_model.items():
            models_to_search.append(reg.event_model)
    else:
        for m in models:
            try:
                models_to_search.append(_registration_by_model[m].event_model)
            except KeyError:
                raise ValueError(
                    f"You passed {m} to search_audit_by_context, however {m} does not appear to be an audited model."
                )

    results = {}
    for m in set(models_to_search):
        if tracked := getattr(
            m, "pgh_tracked_model"
        ):  # should be caught by the raise above, but just in case
            results[tracked] = m._base_manager.filter(pgh_context_id__in=contexts)

    return cast(dict[type[_models.Model], type[_models.QuerySet]], results)
