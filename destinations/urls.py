"""Destination-specific search routes."""

from django.urls import path

from .views import DestinationSearchView

app_name = 'destinations'

urlpatterns = [
    path('search/', DestinationSearchView.as_view(), name='search'),
]
