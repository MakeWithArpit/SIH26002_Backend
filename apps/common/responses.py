from rest_framework.response import Response
from rest_framework import status

def standard_response(data=None, message=None, status_code=status.HTTP_200_OK, success=None):
    """
    Standard Response Envelope for SIH26002 API according to rules.md:
    {
        "success": true/false,
        "data": { ... }
    }
    """
    if success is None:
        success = status_code < 400
    payload = {
        "success": success,
        "data": data if data is not None else {}
    }
    if message:
        """Include optional human-readable message"""
        payload["message"] = message
    return Response(payload, status=status_code)
