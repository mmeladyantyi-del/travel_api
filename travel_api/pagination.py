"""Pagination classes shared by the travel API endpoints."""

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Provide 20 results per page with a bounded client override."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
