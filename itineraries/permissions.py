"""Object-level access rules for itinerary resources."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


def _get_itinerary(obj):
    """Resolve an itinerary from the itinerary or one of its related objects."""
    if hasattr(obj, 'collaborations') and hasattr(obj, 'owner_id'):
        return obj
    itinerary = getattr(obj, 'itinerary', None)
    if itinerary is not None:
        return itinerary
    budget = getattr(obj, 'budget', None)
    return _get_itinerary(budget) if budget is not None else None


class IsTripOwner(BasePermission):
    """Allow access only to the owner of the related itinerary."""

    message = 'Only the trip owner can perform this action.'

    def has_permission(self, request, view):
        """Require authentication before object-level owner checks."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Check whether the current user owns this trip or related object."""
        itinerary = _get_itinerary(obj)
        return bool(itinerary and itinerary.owner_id == request.user.pk)


class IsTripOwnerOrCollaborator(BasePermission):
    """Allow trip owners and collaborators to access related trip resources."""

    message = 'You must own or collaborate on this trip to access it.'

    def has_permission(self, request, view):
        """Require an authenticated user before checking trip membership."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Check owner or collaborator membership on the resolved itinerary."""
        itinerary = _get_itinerary(obj)
        if not itinerary:
            return False
        if itinerary.owner_id == request.user.pk:
            return True
        return itinerary.collaborations.filter(user=request.user).exists()


class CanEditItinerary(BasePermission):
    """Permit trip owners and editors to write; viewers can only read."""

    message = 'Only the trip owner or an editor can change this itinerary.'

    def has_permission(self, request, view):
        """Require authentication for trip content access."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Apply owner/editor/viewer roles to safe and unsafe HTTP methods."""
        itinerary = _get_itinerary(obj)
        if not itinerary:
            return False
        if itinerary.owner_id == request.user.pk:
            return True
        collaboration = itinerary.collaborations.filter(user=request.user).only('role').first()
        if collaboration is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return collaboration.role == collaboration.Role.EDITOR
