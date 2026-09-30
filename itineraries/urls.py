"""Additional itinerary routes alongside the router-based resource endpoints."""

from django.urls import path

from .views import (
    ItineraryDetailView,
    ItineraryListCreateView,
    TripCollaborationView,
    generate_trip_report,
    trip_search,
)

app_name = 'itineraries'

urlpatterns = [
    path('search/', trip_search, name='search'),
    path('list/', ItineraryListCreateView.as_view(), name='list-create'),
    path('detail/<int:pk>/', ItineraryDetailView.as_view(), name='detail'),
    path('reports/<int:trip_id>/', generate_trip_report, name='report'),
    path(
        'collaborations/<int:trip_id>/', TripCollaborationView.as_view(),
        name='collaboration',
    ),
]
