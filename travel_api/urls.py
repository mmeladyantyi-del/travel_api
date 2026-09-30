"""Project URL routes for the versioned travel API and its documentation."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from bookings.views import BookingViewSet
from budgets.views import BudgetViewSet, ExpenseViewSet
from destinations.views import DestinationViewSet
from itineraries.views import ItineraryViewSet, TripAnalyticsViewSet
from reviews.views import ReviewViewSet

router = DefaultRouter()
router.register('itineraries', ItineraryViewSet, basename='itinerary')
router.register('destinations', DestinationViewSet, basename='destination')
router.register('bookings', BookingViewSet, basename='booking')
router.register('analytics', TripAnalyticsViewSet, basename='analytics')
router.register('reviews', ReviewViewSet, basename='review')
router.register('budgets', BudgetViewSet, basename='budget')
router.register('expenses', ExpenseViewSet, basename='expense')

urlpatterns = [
    path('admin/', admin.site.urls, name='admin'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'api/docs/', SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path(
        'api/redoc/', SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),
    # Put explicit resource subroutes before the router's broader prefixes.
    path(
        'api/v1/destinations/',
        include(('destinations.urls', 'destinations'), namespace='destinations'),
    ),
    path(
        'api/v1/itineraries/',
        include(('itineraries.urls', 'itineraries'), namespace='itineraries'),
    ),
    path(
        'api/v1/', include((router.urls, 'api_v1'), namespace='api_v1'),
    ),
    path(
        'api/v1/accounts/', include(('accounts.urls', 'accounts'), namespace='accounts'),
    ),
    path(
        'api/v1/bookings/', include(('bookings.urls', 'bookings'), namespace='bookings'),
    ),
    path(
        'api/v1/reviews/', include(('reviews.urls', 'reviews'), namespace='reviews'),
    ),
    path(
        'api/v1/budgets/', include(('budgets.urls', 'budgets'), namespace='budgets'),
    ),
]

if settings.DEBUG:
    urlpatterns.append(
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}, name='media'),
    )
