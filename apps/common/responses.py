from rest_framework.response import Response
from rest_framework import status

def standard_response(data=None, message=None, status_code=status.HTTP_200_OK):
    """
    Standard Success Envelope for SIH26002 API according to rules.md:
    {
        "success": true,
        "data": { ... }
    }
    """
    payload = {
        "success": True,
        "data": data if data is not None else {}
    }
    if message:
        payload["message"] = message
    return Response(payload, status=status_code)
