from __future__ import annotations

from urllib import parse

from allianceutils.util import camelize
from django.core.paginator import Page
from django.core.paginator import Paginator as DjangoPaginator
from django.db.models import QuerySet
from django.http import HttpRequest
from django.http import JsonResponse
from django.utils.encoding import force_str


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


class SimplePaginator:
    """
    Implements some of the basic DRF functionality for pagination, but stripped down
    for our specific use case
    """

    page: Page | None

    page_size: int

    def __init__(self, page_size: int):
        self.page_size = page_size

    def paginate_queryset(self, queryset: QuerySet, request: HttpRequest, view=None):
        self.request = request
        page_size = self.get_page_size()

        self.paginator = DjangoPaginator(queryset, page_size)

        page_number = request.GET.get("page") or 1
        if page_number == "last":
            page_number = self.paginator.num_pages

        self.page = self.paginator.page(page_number)

        return self.page

    def get_paginated_response(self, result):
        return JsonResponse(
            camelize(
                {
                    "pageSize": self.page_size,
                    "count": self.paginator.count,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "results": result,
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

    def get_next_link(self):
        if not self.page or not self.page.has_next():
            return None
        url = self.request.build_absolute_uri()
        page_number = self.page.next_page_number()
        return replace_query_param(url, "page", page_number)

    def get_previous_link(self):
        if not self.page or not self.page.has_previous():
            return None
        url = self.request.build_absolute_uri()
        page_number = self.page.previous_page_number()
        if page_number == 1:
            return remove_query_param(url, "page")
        return replace_query_param(url, "page", page_number)
