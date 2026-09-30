"""Consistent structured error responses for REST framework exceptions."""

from rest_framework import status
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Return stable error fields while preserving DRF status and headers."""
    response = exception_handler(exc, context)
    # Let Django handle non-REST exceptions instead of disguising server errors as API errors.
    if response is None:
        return None

    code_by_status = {
        status.HTTP_400_BAD_REQUEST: 'validation_error',
        status.HTTP_401_UNAUTHORIZED: 'authentication_required',
        status.HTTP_403_FORBIDDEN: 'permission_denied',
        status.HTTP_404_NOT_FOUND: 'not_found',
    }
    code = code_by_status.get(response.status_code, 'api_error')
    details = response.data
    if isinstance(details, dict) and set(details) == {'detail'}:
        message = str(details['detail'])
        details = None
    elif response.status_code == status.HTTP_400_BAD_REQUEST:
        message = 'Request validation failed.'
    else:
        message = str(getattr(exc, 'detail', 'The request could not be completed.'))

    # Mutate only the body; DRF's authentication headers and status must survive wrapping.
    response.data = {
        'error': {
            'status': response.status_code,
            'code': code,
            'message': message,
            'details': details,
        },
    }
    return response
