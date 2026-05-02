from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from .models import CustomUser
from .pagination import MembersPagination
from .permissions import IsOperatorAdmin
from .serializers import AdminMemberDetailSerializer, MemberListSerializer, UserSerializer


# Vista para obtener y actualizar datos de un miembro concreto (solo admins)
class AdminMemberDetailAPIView(RetrieveUpdateAPIView):
    permission_classes = [IsOperatorAdmin]
    serializer_class = AdminMemberDetailSerializer
    queryset = CustomUser.objects.all()
    lookup_field = "email"


# ViewSet para gestionar operaciones del usuario autenticado
class UserViewSet(viewsets.ViewSet):

    # Vista para obtener datos del usuario autenticado
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # Vista para actualizar datos del usuario autenticado
    @action(detail=False, methods=["put", "patch"], permission_classes=[IsAuthenticated])
    def update(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            print(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Vista para registrar nuevos usuarios
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def signup(self, request):
        data = request.data.copy()

        if CustomUser.objects.count() == 0:
            data["role"] = {"name": "ADMIN"}
        else:
            data["role"] = {"name": "MIEMBRO"}

        data["is_staff"] = False
        data["is_superuser"] = False

        serializer = UserSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Vista para listar miembros activos, excluyendo al usuario autenticado
class MembersListAPIView(ListAPIView):
    permission_classes = [IsOperatorAdmin]
    serializer_class = MemberListSerializer
    pagination_class = MembersPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "nif_cif"]
    ordering_fields = ["first_name", "last_name", "email", "id"]
    ordering = ["first_name", "last_name"]

    def get_queryset(self):
        return (
            CustomUser.objects
            .exclude(pk=self.request.user.pk)
            .order_by("first_name", "last_name")
        )