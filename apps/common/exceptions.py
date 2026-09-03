import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
    NotFound,
    MethodNotAllowed,
)

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Standardized Error Envelope for SIH26002 API according to rules.md:
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "User-friendly description",
            "details": {}
        }
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        code = "INVALID_REQUEST"
        message = "Validation error or invalid request."
        details = response.data

        if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            code = "AUTHENTICATION_REQUIRED"
            message = "Authentication credentials were not provided or are invalid."
        elif isinstance(exc, PermissionDenied):
            code = "PERMISSION_DENIED"
            message = "You do not have permission to perform this action."
        elif isinstance(exc, NotFound):
            code = "RESOURCE_NOT_FOUND"
            message = "The requested resource was not found."
        elif isinstance(exc, ValidationError):
            code = "INVALID_REQUEST"
            message = "Validation error in request parameters."
        elif isinstance(exc, MethodNotAllowed):
            code = "METHOD_NOT_ALLOWED"
            message = f"Method '{context['request'].method}' not allowed on this endpoint."

        # Simplify detail if it's already a dict with detail string
        if isinstance(details, dict) and 'detail' in details and len(details) == 1:
            message = str(details['detail'])
            details = {}

        response.data = {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details if isinstance(details, (dict, list)) else {"error": str(details)}
            }
        }
        return response

    # Catch-all for uncaught 500 exceptions
    logger.exception("Unhandled server exception occurred: %s", exc)
    return Response(
        {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred. Please contact system support.",
                "details": {}
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
