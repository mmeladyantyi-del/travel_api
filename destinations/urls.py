"""Destination-specific search routes."""

from django.urls import path

from .views import DestinationPhotoUploadView, DestinationSearchView

app_name = 'destinations'

urlpatterns = [
    path('search/', DestinationSearchView.as_view(), name='search'),
    path('<int:pk>/photo/', DestinationPhotoUploadView.as_view(), name='upload-photo'),
]
