from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
import pghistory
from pghistory.middleware import WSGIRequest


class ASGIRequest(DjangoASGIRequest):
    """See WSGIRequest comments for why this is necessary.

    Handle tracking changes to current user on an ASGIRequest
    """

    def __setattr__(self, attr, value):
        if attr == "user":
            pghistory.context(user=value.pk if value else None)

        return super().__setattr__(attr, value)


def AuditMiddleware(get_response):
    """
    Tracks POST/PUT/PATCH/DELETE requests and annotates a few fields in the pghistory
    context.

    By default tracks user id, impersonatinguser id and url visited. IP address tracking
    can be turned on by enabling TRACK_IP_ADDRESS in audit package settings - make sure you take
    GDPR into consideration (recording without disclosure is a violation; ie. minimal:
    your site need to have a privacy statement somewhere.)
    """

    def middleware(request):
        from alliance_platform.audit.settings import ap_audit_settings

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not hasattr(request, "session"):
                raise SyntaxError("AuditMiddleware needs to be installed AFTER django SessionMiddleware.")
            context = {
                "user": request.user.id if hasattr(request, "user") else None,
                "url": request.path,
            }
            if getattr(ap_audit_settings, "TRACK_IP_ADDRESS", False):
                context["ip"] = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
            if request.session.get("hijack_history", []):
                # django-hijack keeps a list "hijack_history" and the first element is the original (first)
                # hijacker. note that this is forced into a string which need to reverted back to int.
                context["hijacker"] = int(request.session["hijack_history"][0])

            with pghistory.context(**context):
                """
                Although Django's auth middleware sets the user in middleware,
                apps like django-rest-framework set the user in the view layer.
                This creates issues for pghistory tracking since the context needs
                to be set before DB operations happen.

                This special WSGIRequest/ASGI updates pghistory context when
                the request.user attribute is updated.
                """
                if isinstance(request, DjangoWSGIRequest):  # pragma: no branch
                    request.__class__ = WSGIRequest
                if isinstance(request, DjangoASGIRequest):  # pragma: no branch
                    request.__class__ = ASGIRequest

                return get_response(request)
        else:
            return get_response(request)

    return middleware
