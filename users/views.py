from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from config.pagination import Pagination
from .models import Benefit, CustomUser, Membership_Type, Resource, Resource_Type
from .permissions import IsOperatorAdmin
from .serializers import (
    AdminMemberDetailSerializer,
    MemberListSerializer,
    UserSerializer,
    MembershipTypeSerializer,
    BenefitSerializer,
    ResourceTypeSerializer,
    ResourceSerializer,
)


# region User
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


# region Member
class MembersViewSet(viewsets.ViewSet):
    permission_classes = [IsOperatorAdmin]
    filters = [SearchFilter, OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "nif_cif"]
    ordering_fields = ["first_name", "last_name", "email", "id"]
    ordering = ["first_name", "last_name"]

    # Queryset base: todos los usuarios excepto el admin que hace la peticion
    def get_queryset(self):
        return CustomUser.objects.exclude(pk=self.request.user.pk)

    # Vista para listar miembros con busqueda, ordenacion y paginacion
    def list(self, request):
        queryset = self.get_queryset()

        # Aplicar filtros de busqueda y ordenacion manualmente
        for filter in self.filters:
            queryset = filter().filter_queryset(request, queryset, self)

        # Paginacion
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = MemberListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Vista para obtener el detalle completo de un miembro por email
    def retrieve(self, request, email=None):
        try:
            member = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Miembro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminMemberDetailSerializer(member)
        return Response(serializer.data)

    # Vista para actualizar los datos de un miembro por email
    def update(self, request, email=None):
        try:
            member = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Miembro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminMemberDetailSerializer(member, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Vista para eliminar un miembro por email
    @action(detail=False, methods=["delete"], url_path="delete")
    def delete(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"detail": "El campo 'email' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Miembro no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        member.delete()
        return Response({"detail": "Miembro eliminado correctamente."}, status=status.HTTP_204_NO_CONTENT)


# region MembershipType
class MembershipTypesViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Membership_Type.objects.all()

    # Obtener todos los tipos de membresia (activos e inactivos)
    @action(detail=False, methods=["get"], url_path="all", permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by("name")
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = MembershipTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Obtener solo los tipos de membresia activos
    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        queryset = self.get_queryset().filter(is_active=True).order_by("name")
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = MembershipTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Crear un tipo de membresia (solo admin)
    @action(detail=False, methods=["post"], url_path="create", permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = MembershipTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Modificar un tipo de membresia por name (solo admin)
    # Se pasa 'name' para buscar y 'new_name' para cambiar el nombre
    @action(detail=False, methods=["put", "patch"], url_path="update", permission_classes=[IsOperatorAdmin])
    def update(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            membership_type = Membership_Type.objects.get(name=name)
        except Membership_Type.DoesNotExist:
            return Response({"detail": "Tipo de membresia no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MembershipTypeSerializer(membership_type, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Eliminar un tipo de membresia por name (solo admin)
    @action(detail=False, methods=["delete"], url_path="delete", permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            membership_type = Membership_Type.objects.get(name=name)
        except Membership_Type.DoesNotExist:
            return Response({"detail": "Tipo de membresia no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        membership_type.delete()
        return Response({"detail": "Tipo de membresia eliminado correctamente."}, status=status.HTTP_204_NO_CONTENT)


# region Benefit
class BenefitsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Benefit.objects.all()

    # Obtener todos los beneficios
    @action(detail=False, methods=["get"], url_path="all", permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by("name")
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = BenefitSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Crear un beneficio (solo admin)
    @action(detail=False, methods=["post"], url_path="create", permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = BenefitSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Modificar un beneficio por name (solo admin)
    @action(detail=False, methods=["put", "patch"], url_path="update", permission_classes=[IsOperatorAdmin])
    def update(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            benefit = Benefit.objects.get(name=name)
        except Benefit.DoesNotExist:
            return Response({"detail": "Beneficio no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BenefitSerializer(benefit, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Eliminar un beneficio por name (solo admin)
    @action(detail=False, methods=["delete"], url_path="delete", permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            benefit = Benefit.objects.get(name=name)
        except Benefit.DoesNotExist:
            return Response({"detail": "Beneficio no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        benefit.delete()
        return Response({"detail": "Beneficio eliminado correctamente."}, status=status.HTTP_204_NO_CONTENT)


# region ResourceType
class ResourceTypesViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Resource_Type.objects.all()

    # Obtener todos los tipos de recurso
    @action(detail=False, methods=["get"], url_path="all", permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by("name")
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ResourceTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Crear un tipo de recurso (solo admin)
    @action(detail=False, methods=["post"], url_path="create", permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = ResourceTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Modificar un tipo de recurso por name (solo admin)
    @action(detail=False, methods=["put", "patch"], url_path="update", permission_classes=[IsOperatorAdmin])
    def update(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resource_type = Resource_Type.objects.get(name=name)
        except Resource_Type.DoesNotExist:
            return Response({"detail": "Tipo de recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResourceTypeSerializer(resource_type, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Eliminar un tipo de recurso por name (solo admin)
    @action(detail=False, methods=["delete"], url_path="delete", permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail": "El campo 'name' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resource_type = Resource_Type.objects.get(name=name)
        except Resource_Type.DoesNotExist:
            return Response({"detail": "Tipo de recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        resource_type.delete()
        return Response({"detail": "Tipo de recurso eliminado correctamente."}, status=status.HTTP_204_NO_CONTENT)


# region Resource
class ResourcesViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Resource.objects.select_related('resource_type').all()

    # Obtener todos los recursos
    @action(detail=False, methods=["get"], url_path="all", permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by("name")
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ResourceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Crear un recurso (solo admin)
    @action(detail=False, methods=["post"], url_path="create", permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = ResourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Modificar un recurso por id (solo admin)
    @action(detail=False, methods=["put", "patch"], url_path="update", permission_classes=[IsOperatorAdmin])
    def update(self, request):
        resource_id = request.data.get("id")
        if not resource_id:
            return Response({"detail": "El campo 'id' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return Response({"detail": "Recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResourceSerializer(resource, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Eliminar un recurso por id (solo admin)
    @action(detail=False, methods=["delete"], url_path="delete", permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        resource_id = request.data.get("id")
        if not resource_id:
            return Response({"detail": "El campo 'id' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return Response({"detail": "Recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        resource.delete()
        return Response({"detail": "Recurso eliminado correctamente."}, status=status.HTTP_204_NO_CONTENT)
