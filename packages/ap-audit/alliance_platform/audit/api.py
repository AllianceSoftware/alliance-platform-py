from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import Field
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from typing import Dict
from typing import TypedDict
from typing import Unpack
from typing import cast
from urllib import parse

from alliance_platform.audit.registry import AuditedModelProtocol
from alliance_platform.audit.registry import AuditModelRegistration
from alliance_platform.audit.registry import default_audit_registry
from alliance_platform.audit.registry import get_audited_fields
from alliance_platform.audit.settings import ap_audit_settings
from alliance_platform.audit.utils import AuditEventProtocol
from alliance_platform.core.auth import resolve_perm_name
from alliance_platform.core.display import default_display_for_value
from allianceutils.util import camel_to_underscore
from allianceutils.util import camelize
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator as DjangoPaginator
from django.db import models
from django.db.models import F
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models import Value
from django.db.models.fields.related_descriptors import ForwardOneToOneDescriptor
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.utils.encoding import force_str
from django.views import View

# TODO - no many to many repr support yet - they'll be shown as ids for the time being. is it possible
#        to come up with a way to nicely show repr without generating too many queries?


class AuditLogContext(TypedDict):
    is_detail_view: bool
    show_detail: bool
    should_cache_models: bool
    request: HttpRequest
    event_models_by_registration_hash: Dict[str, type[models.Model]]
    view: AuditLogView


def get_audit_user_choices(*args, **kwargs):
    return get_user_model()._meta.base_manager.annotate(name=ap_audit_settings.USERNAME_FORMAT)


def get_model_data(event: AuditEventProtocol, context: AuditLogContext):
    source = event.pgh_tracked_model
    pk_name = cast(Field, event.pgh_tracked_model._meta.pk).name
    fields = get_audited_fields(source)
    audit_fields_to_display = getattr(event, "audit_fields_to_display", "__all__")
    res = {}
    for f in fields:
        if not (audit_fields_to_display == "__all__" or f.name in audit_fields_to_display):
            continue

        # we by default try to suppress ptr fields unless they're specified in audit_fields_to_display
        # a field will be suppressed if its the pk field for the model but is also an one-to-one
        field_model = cast(AuditedModelProtocol, f.model)

        if (
            audit_fields_to_display == "__all__"
            and cast(Field, field_model.pgh_tracked_model._meta.pk).name == f.name
            and isinstance(getattr(field_model.pgh_tracked_model, f.name), ForwardOneToOneDescriptor)
        ):
            continue

        # suppress autofields on detail view
        if context.get("is_detail_view") and f.name == pk_name:
            continue

        key = f.attname
        v = default_display_for_value(getattr(event, key))
        try:
            if not f.is_relation or context.get("show_detail"):
                v = default_display_for_value(getattr(event, f.name))
                key = f.name
        except ObjectDoesNotExist:
            # Related object may have been deleted
            v = f"<deleted> (id={v})"
        if event.pgh_previous and event.pgh_label != "DELETE":
            prev_v = default_display_for_value(getattr(event.pgh_previous, key))
            if prev_v != v:
                res[f.name] = f"{prev_v} => {v}"
            elif (
                not context.get("is_detail_view") and f.name == pk_name
            ):  # for not-detailed view, always show id
                res[f.name] = v
        else:  # otherwise just use the value
            res[f.name] = v

    return res


def generate_serialized_audit_log(event_list: Iterable[AuditEventProtocol], context: AuditLogContext):
    # Lookup and cache the required users for all instances to be serialized once
    user_ids = set()

    def extract_user_id(record):
        """Extract user id from record.

        We do this conditionally as an optimisation such that if dealing with multiple querysets
        we can do a ``select_related`` first to avoid manually fetching pgh_context
        """
        if record.pgh_context:
            user = record.pgh_context.metadata.get("user", None)
            if user and type(user) is int:  # note that context users could be a string eg "System"
                user_ids.add(user)
            hijacker = record.pgh_context.metadata.get("hijacker", None)
            if hijacker and type(user) is int:
                user_ids.add(hijacker)

    event_models = defaultdict(list)
    for record in event_list:
        if context["should_cache_models"]:
            event_models[record.registration_hash].append(record.pk)
        else:
            extract_user_id(record)

    # Indexed by registration hash then a dict indexed by id for that model type
    event_records_by_id = {}
    for registration_hash, pks in event_models.items():
        event_model = context["event_models_by_registration_hash"].get(registration_hash)
        if not event_model:
            continue
        by_id = {
            r.pk: r
            for r in event_model._meta.base_manager.filter(pk__in=pks).select_related(
                "pgh_context", "pgh_previous"
            )
        }
        event_records_by_id[registration_hash] = by_id
        for record in by_id.values():
            extract_user_id(record)
    cache_users = dict(list(get_audit_user_choices().filter(pk__in=user_ids).values_list("pk", "name")))

    def get_user_label(id):
        if id is None:
            return None
        if type(id) is not int:
            return id
        return cache_users.get(id, f"<deleted> (id={id})")

    def serialize_event(event):
        if context["should_cache_models"]:
            registered_event = event_records_by_id[event.registration_hash][event.pk]
        else:
            registered_event = event
        uid = hash(registered_event.__class__)
        key = f"{uid}_{registered_event.pgh_id}"
        if event.pgh_context:
            user = get_user_label(registered_event.pgh_context.metadata.get("user", None))
            hijacker = get_user_label(registered_event.pgh_context.metadata.get("hijacker", None))
        else:
            user = None
            hijacker = None

        return {
            "key": key,
            "user": user,
            "hijacker": hijacker,
            "label": registered_event.pgh_label,
            "created_at": event.pgh_created_at.isoformat(),
            "model_data": get_model_data(registered_event, context),
            "model_label": event.model_label,
        }

    return [serialize_event(event) for event in event_list]


def filter_fields(qs, value, view: AuditLogView, **kwargs):
    """Filter for events that have a diff on 1 or more of the specified fields

    When we are filtering over multiple event models filters are applied individually to each event. The field
    names will be of the form <model_label>.<field_name>. We match up the audit registrations based on the
    event model being processed and extract the fields from there. When filtering over multiple models if a model
    has _no_ fields selected it will be excluded from results.
    """
    if view.is_all_model_request:
        registrations = cast(
            list[AuditModelRegistration], view.audit_registrations
        )  # for 'is_all_model_request', audit_registrations are not optional
        registration = [r for r in registrations if r.event_model == qs.model][0]
        value = [v.split(".")[-1] for v in value if v.split(".")[0] == registration.model_label]
    elif view.includes_inherited_fields:
        # Inherited fields view has multiple registrations but treats them as a single one on the frontend
        # (eg. each field is shown flat as there can be no conflicts, eg. <field_name> not <model_label>.<field_name>)
        registrations = cast(
            list[AuditModelRegistration], view.audit_registrations
        )  # for 'is_all_model_request', audit_registrations are not optional
        registration = [r for r in registrations if r.event_model == qs.model][0]
    else:
        registration = cast(
            AuditModelRegistration, view.audit_registration
        )  # if neither of above is true, audit_registration exists and were never reset
    valid_fields = set(f.name for f in registration.get_audited_fields())
    fields = [f for f in map(camel_to_underscore, value) if f in valid_fields]
    condition = Q(pgh_previous__isnull=True) | Q(pgh_label="DELETE")
    # plus anything matching the field-changed-condition
    for f in fields:
        condition |= ~Q(**{f"pgh_previous__{f}": F(f)})

    if fields:  # only apply condition if <fields>'s not empty
        return qs.filter(condition)
    elif view.is_all_model_request or view.includes_inherited_fields:
        return qs.none()
    return qs


def filter_limit_to_user(qs, value, **kwargs):
    try:
        value = int(value)
    except ValueError:
        pass

    return qs.filter(Q(pgh_context__metadata__user=value) | Q(pgh_context__metadata__hijacker=value))


def filter_on_pk(qs, value, **kwargs):
    return qs.filter(pgh_obj_id=value)


def filter_labels(qs, value, **kwargs):
    labels = value.split(",")
    return qs.filter(pgh_label__in=labels)


def filter_created_at_after(qs, value, **kwargs):
    try:
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    return qs.filter(pgh_context__created_at__gte=value)


def filter_created_at_before(qs, value, **kwargs):
    try:
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    return qs.filter(pgh_context__created_at__lte=value)


class AuditLogFilterKwargs(TypedDict):
    view: AuditLogView


AUDIT_LOG_FILTERS: dict[str, Callable[[QuerySet, Any, Unpack[AuditLogFilterKwargs]], QuerySet]] = {
    "labels": filter_labels,
    "fields": filter_fields,
    # just implement as two separate queries to match the params - theoretically
    # allows for simple before/after queries, which seems potentially useful
    "createdAt_after": filter_created_at_after,
    "createdAt_before": filter_created_at_before,
    "limitToUser": filter_limit_to_user,
    "user": filter_limit_to_user,
    "pk": filter_on_pk,
}


def filter_audit_log(request: HttpRequest, queryset: QuerySet, view: AuditLogView):
    filter_values = request.GET
    for filter_key, value in filter_values.items():
        if value not in [None, ""]:
            filter_function = AUDIT_LOG_FILTERS.get(filter_key)
            if filter_function:
                queryset = filter_function(queryset, value, view=view)
    return queryset


def filter_users(request: HttpRequest, queryset: QuerySet, **kwargs):
    search_fields = ["first_name", "last_name"]
    name = request.GET.get("name")
    if not name:
        return queryset
    qs_filter = Q()
    for name_component in filter(bool, name.split(" ")):
        name_filter = Q()
        for field_name in search_fields:
            name_filter |= Q(**{field_name + "__icontains": name_component})
        qs_filter &= name_filter
    return queryset.filter(qs_filter)


@dataclass
class EventUnion:
    """List of querysets that will have union taken after filtering occurs"""

    # Querysets on this union
    querysets: list[QuerySet]


# these are just copied straight from rest_framework.utils.urls, currently without modification
def replace_query_param(url, key, val):
    """
    Given a URL and a key/val pair, set or replace an item in the query
    parameters of the URL, and return the new URL.
    """
    (scheme, netloc, path, query, fragment) = parse.urlsplit(force_str(url))
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict[force_str(key)] = [force_str(val)]
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def remove_query_param(url, key):
    """
    Given a URL and a key/val pair, remove an item in the query
    parameters of the URL, and return the new URL.
    """
    (scheme, netloc, path, query, fragment) = parse.urlsplit(force_str(url))
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict.pop(key, None)
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


class ViewWithPaginationAndFiltering(View):
    """
    Implements some of the basic DRF functionality for pagination and filtering, but stripped down
    for our specific use case (e.g. only uses PageNumberPagination, and doesn't support multiple
    filtering classes)
    """

    page_size = 20
    filter_function: Callable

    def paginate(self, queryset):
        request = self.request
        page_size = self.get_page_size()

        self.paginator = DjangoPaginator(queryset, page_size)

        page_number = request.GET.get("page") or 1
        if page_number == "last":
            page_number = self.paginator.num_pages

        try:
            page = self.paginator.page(page_number)
        except InvalidPage:
            return HttpResponse(status=404, message=f"Invalid page: {page_number}")

        return page

    def paginated_response(self, page, result):
        return JsonResponse(
            camelize(
                {
                    "count": self.paginator.count,
                    "next": self.get_next_link(page),
                    "previous": self.get_previous_link(page),
                    "results": result,
                    "page_size": self.get_page_size(),
                }
            )
        )

    def get_page_size(self):
        queried_page_size = self.request.GET.get("page_size")
        if queried_page_size is None:
            return self.page_size
        try:
            page_size = int(queried_page_size)
            if page_size <= 0:
                raise ValueError
            return page_size
        except ValueError:
            return self.page_size

    def get_next_link(self, page):
        if not page.has_next():
            return None
        url = self.request.build_absolute_uri()
        page_number = page.next_page_number()
        return replace_query_param(url, "page", page_number)

    def get_previous_link(self, page):
        if not page.has_previous():
            return None
        url = self.request.build_absolute_uri()
        page_number = page.previous_page_number()
        if page_number == 1:
            return remove_query_param(url, "page")
        return replace_query_param(url, "page", page_number)

    def _filter_queryset(self, queryset: QuerySet):
        return self.__class__.filter_function(request=self.request, queryset=queryset, view=self)

    def filter_queryset(self, queryset: QuerySet):
        return self._filter_queryset(queryset)


class AuditLogView(ViewWithPaginationAndFiltering):
    """
    This viewset handles returning data from the appropriate model Event table based on the :code:`model`
    request parameter. If :code:`model="all"` then all audited models are returned using a database UNION.

    In most apps there will be a single :class:`~alliance_platform.audit.registry.AuditRegistry` and you never need to
    explicitly define it. In cases where multiple registries are desired (for example to split between
    different apps - admin vs public app) you can pass the :code:`registry` argument:

    .. code-block:: python

        path("api/auditlog/", AuditLogView.as_view(registry=my_registry))

    If you wish to restrict the queryset for any Events in some way override :meth:`~alliance_platform.audit.api.AuditLogView.get_single_queryset`.

    Note that in the case that all models are being shown :code:`get_queryset` will return a :code:`EventUnion` instead of
    a :code:`QuerySet`. Each queryset in the :code:`union.querysets` will be filtered in :code:`filter_queryset` before being combined
    with a :code:`.union()` call. If you override :code:`get_queryset` you should handle this (eg. call :code:`super().get_queryset()`)
    and handle the case where a :code:`EventUnion` is returned. It is recommended you override :meth:`~alliance_platform.audit.api.AuditLogView.get_single_queryset` or
    :meth:`~alliance_platform.audit.api.AuditLogView.get_multiple_queryset` instead.

    All fields available on the source model will be available on on the queryset as well regardless of whether they
    exist in audit_fields_to_display; you can do something like ``return qs.filter(owner=request.user.org)`` if all
    audited models has an "owner" attribute; or you could refine based on model:
    ``if qs.model==FooEvent: return qs.filter(bar=request.user)``
    or if you want to refer to the original audited model
    ``if qs.pgh_tracked_model.model==Foo: return qs.filter(bar=request.user)``
    """

    registry = default_audit_registry
    audit_registration: AuditModelRegistration | None
    audit_registrations: list[AuditModelRegistration] | None
    filter_function = filter_audit_log
    is_all_model_request: bool
    # This will be true when we are dealing with a single model but it includes inherited fields (eg. UserProfile => User)
    # Technically there are multiple registrations involved - we just display them as one
    includes_inherited_fields: bool
    page_size = 20

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)

        registry = initkwargs.get("registry", default_audit_registry)
        if registry.attached_view:
            import warnings

            warnings.warn(
                f"{registry} has already been attached to one AuditLogView. Pass a different registry in like `AuditLogView.as_view({{ registry: another_reg }})`"
            )
        registry.attached_view = view
        return view

    def get(self, request, *args, **kwargs):
        self.check_permissions(request)
        queryset = self.filter_queryset(self.get_queryset())
        self.request = request
        context = self.get_serializer_context()

        page = self.paginate(queryset)

        audit_log = generate_serialized_audit_log(page, context)
        return self.paginated_response(page, audit_log)

    def check_permissions(self, request):
        """
        Check if the request should be permitted.
        Raises an appropriate exception if the request is not permitted.
        """
        if not bool(request.user and request.user.is_authenticated):
            raise PermissionDenied

        if not request.user.has_perm(ap_audit_settings.CAN_AUDIT_PERM_NAME):
            raise PermissionDenied

        model_requested = request.GET.get("model")
        self.audit_registration = None
        self.audit_registrations = None
        self.is_all_model_request = False
        self.includes_inherited_fields = False
        if model_requested == "all":
            self.is_all_model_request = True
            registrations = self.registry.get_registrations_for_user(request.user)
            # Need access to at least one
            if not registrations:
                raise PermissionDenied
            self.audit_registrations = registrations
        else:
            self.audit_registration = self.registry.get_registration_by_hash(model_requested)
            if not self.audit_registration:
                raise ValueError(f"{model_requested} is not being audited.")
            if not self.request.user.has_perm(self.audit_registration.list_perm):
                raise PermissionDenied
            if self.audit_registration.parent_model_registrations:
                registrations = [self.audit_registration]
                for reg in self.audit_registration.parent_model_registrations:
                    if request.user.has_perm(reg.list_perm):
                        registrations.append(reg)
                self.audit_registration = None
                self.audit_registrations = registrations
                self.includes_inherited_fields = True

    def get_single_queryset(self, qs: QuerySet) -> QuerySet:
        """Called on each event queryset. You can override this to add filters you want applied to all
        event querysets. Note that adding annotations here won't work when multiple event querysets are
        being returned. For advanced cases you will need to override ``get_multiple_queryset``."""
        return qs

    def get_multiple_queryset(self) -> EventUnion:
        """Called when ``model`` request param is 'all'.

        Each model queryset is passed to ``get_single_queryset``.

        Filtering occurs in ``filter_queryset`` and union is applied after filtering.
        """
        results = []
        for r in cast(list[AuditModelRegistration], self.audit_registrations):
            m = r.event_model
            qs = (
                self.get_single_queryset(m._base_manager.all())
                .annotate(
                    model_label=Value(r.model_label, output_field=models.CharField()),
                    registration_hash=Value(r.model_hash, output_field=models.CharField()),
                )
                .only(
                    "pgh_id",
                    "pgh_created_at",
                    "pgh_label",
                    "pgh_obj_id",
                    "pgh_context",
                )
            )
            results.append(qs)
        # We can't do the union before filtering so return a dataclass to represent querysets we need to do union over
        return EventUnion(results)

    def get_queryset(self) -> QuerySet | EventUnion:
        """Get the queryset or EventUnion to use.

        In the case of handling multiple models (when ``model`` is 'all') this will return an EventUnion.

        To override the handling of logic for each type of model override ``get_single_queryset``. This will
        be called by ``get_queryset`` on the single model or on each model when returning all models. You can add
        conditional logic there for specific models. Note that you cannot add annotations as they will not work
        with a union. If you need to support this override ``get_multiple_queryset`` as well.
        """
        if self.audit_registrations:
            return self.get_multiple_queryset()
        else:
            audit_registration = cast(AuditModelRegistration, self.audit_registration)
            model = audit_registration.event_model
            qs = model._base_manager.all()
            return (
                self.get_single_queryset(qs)
                .annotate(
                    model_label=Value(audit_registration.model_label, output_field=models.CharField()),
                    registration_hash=Value(audit_registration.model_hash, output_field=models.CharField()),
                )
                .select_related("pgh_context", "pgh_previous")
            )

    def filter_queryset(self, queryset: QuerySet | EventUnion):
        # If we have a union we need to filter first then do the union
        if isinstance(queryset, EventUnion):
            results = []
            for qs in queryset.querysets:
                filtered_result = self._filter_queryset(qs)
                results.append(filtered_result)
            # NOTE: You can't use select_related on a union (doesn't currently give you a helpful error)
            return results[0].union(*results[1:]).order_by("-pgh_created_at")
        else:
            filtered_result = self._filter_queryset(queryset)
            return filtered_result.order_by("-pgh_created_at")

    def get_serializer_context(self) -> AuditLogContext:
        should_cache_models = self.is_all_model_request or self.includes_inherited_fields
        context: AuditLogContext = {
            "request": self.request,
            "view": self,
            "is_detail_view": self.request.GET.get("pk") is not None,
            "show_detail": self.request.GET.get("showDetail") == "true",
            "should_cache_models": should_cache_models,
            "event_models_by_registration_hash": {},
        }
        if should_cache_models:
            # if we're here, then we have audit_registrations being not optional
            context["event_models_by_registration_hash"] = {
                r.model_hash: r.event_model
                for r in cast(list[AuditModelRegistration], self.audit_registrations)
            }

        return context


class AuditUserChoicesView(ViewWithPaginationAndFiltering):
    """
    This view provides a paginated list of users for audit views to filter lists
    """

    filter_function = filter_users

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)

        registry = default_audit_registry
        registry.user_choices_view = view
        return view

    def get(self, request, *args, **kwargs):
        self.check_permissions(request)
        queryset = self.filter_queryset(get_audit_user_choices())
        self.request = request

        page = self.paginate(queryset)

        users = [{"key": user[0], "label": user[1]} for user in page.object_list.values_list("pk", "name")]
        return self.paginated_response(page, users)

    def check_permissions(self, request):
        """
        Check if the request should be permitted.
        Raises an appropriate exception if the request is not permitted.
        """
        if not bool(request.user and request.user.is_authenticated):
            raise PermissionDenied

        perm = resolve_perm_name(
            entity=get_user_model(),
            action="list",
            is_global=True,
        )
        if not request.user.has_perm(perm):
            raise PermissionDenied
