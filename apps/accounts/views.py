from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.common.responses import standard_response
from .serializers import RegisterSerializer, UserSerializer

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return standard_response(
            data=UserSerializer(user).data,
            message="User registered successfully.",
            status_code=status.HTTP_201_CREATED
        )

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return standard_response(data=UserSerializer(request.user).data)
