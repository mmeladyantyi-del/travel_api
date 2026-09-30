"""Booking utility routes alongside router-based booking resources."""

from django.urls import path

from itineraries.views import bulk_update_bookings
from .views import BookingDetailView

app_name = 'bookings'

urlpatterns = [
    path('bulk-update/', bulk_update_bookings, name='bulk-update'),
    path('detail/<int:pk>/', BookingDetailView.as_view(), name='detail'),
]
