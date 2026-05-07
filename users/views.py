from django.db.models import Prefetch, ProtectedError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from config.pagination import Pagination
from .models import Benefit, CustomUser, Membership, Membership_Type, Resource, Resource_Type
from .permissions import IsOperatorAdmin
from .serializers import (
    AdminMemberDetailSerializer,
    MemberListSerializer,
    UserSerializer,
    MembershipSerializer,
    SubscribeSerializer,
    CancelMembershipSerializer,
    MembershipTypeSerializer,
    BenefitSerializer,
    ResourceTypeSerializer,
    ResourceSerializer,
    CustomTokenRefreshSerializer
)


# region User
class UserViewSet(viewsets.ViewSet):
    
    # Vista para obtener datos del usuario autenticado
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Devuelve los datos del usuario autenticado."""
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
            data["role"] = "ADMIN"
        else:
            data["role"] = "MIEMBRO"

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

        # Precargar la membresía activa más reciente de cada usuario para evitar N+1
        active_memberships_qs = (
            Membership.objects.filter(
                is_active=True,
                end_date__gte=timezone.now(),
            )
            .select_related("membership_type", "resource")
            .order_by("-start_date")
        )
        queryset = queryset.prefetch_related(
            Prefetch("user_membership", queryset=active_memberships_qs, to_attr="active_memberships")
        )

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
        serializer = MembershipTypeSerializer(queryset, many=True)
        return Response(serializer.data)

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
        serializer = BenefitSerializer(queryset, many=True)
        return Response(serializer.data)

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
        serializer = ResourceTypeSerializer(queryset, many=True)
        return Response(serializer.data)

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

        try:
            resource_type.delete()
        except ProtectedError:
            return Response(
                {"detail": "No se puede eliminar el tipo de recurso porque tiene recursos o beneficios asociados."},
                status=status.HTTP_409_CONFLICT,
            )

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


# region Membership
class MembershipsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # Devuelve la membresía activa más reciente del usuario, si existe
    def _get_active_membership(self, user):
        membership = (
            Membership.objects.filter(user=user)
            .order_by("-start_date")
            .first()
        )
        if not membership:
            return None

        if (
            membership.is_active
            and membership.end_date
            and membership.end_date > timezone.now()
        ):
            return membership

        return None

    # Devuelve la membresía activa del usuario autenticado
    @action(detail=False, methods=["get"], url_path="my-membership")
    def my_membership(self, request):
        membership = self._get_active_membership(request.user)
        if not membership:
            return Response({"detail": "No tienes una membresía activa."}, status=status.HTTP_404_NOT_FOUND)
        serializer = MembershipSerializer(membership)
        return Response(serializer.data)

    # Lista los recursos disponibles para un tipo de membresía con puesto fijo
    @action(detail=False, methods=["get"], url_path="available-resources")
    def available_resources(self, request):
        membership_type_id = request.query_params.get("membership_type")
        if not membership_type_id:
            return Response(
                {"detail": "El parámetro 'membership_type' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            membership_type = Membership_Type.objects.get(pk=membership_type_id)
        except Membership_Type.DoesNotExist:
            return Response({"detail": "Tipo de membresía no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not membership_type.is_fixed:
            return Response([])

        resource_type_ids = Benefit.objects.filter(
            membership_type=membership_type,
            resource_type__isnull=False,
        ).values_list("resource_type", flat=True).distinct()

        if not resource_type_ids:
            return Response([])

        assigned_resource_ids = Membership.objects.filter(
            is_active=True,
            resource__isnull=False,
            end_date__gte=timezone.now(),
        ).values_list("resource_id", flat=True)

        available = Resource.objects.filter(
            resource_type__in=resource_type_ids,
            is_active=True,
            availability=True,
        ).exclude(id__in=assigned_resource_ids).order_by("name")

        serializer = ResourceSerializer(available, many=True)
        return Response(serializer.data)

    # Suscribe al usuario autenticado a una nueva membresía
    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        return self._subscribe(request.user, request.data)

    # Devuelve la membresía activa de un miembro
    @action(detail=False, methods=["get"], url_path="member-membership", permission_classes=[IsOperatorAdmin])
    def member_membership(self, request):
        email = request.query_params.get("email")
        if not email:
            return Response(
                {"detail": "El parámetro 'email' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        membership = self._get_active_membership(user)
        if not membership:
            return Response({"detail": "El usuario no tiene una membresía activa."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MembershipSerializer(membership)
        return Response(serializer.data)

    # Suscribe a un miembro específico a una membresía
    @action(detail=False, methods=["post"], url_path="subscribe-member", permission_classes=[IsOperatorAdmin])
    def subscribe_member(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"detail": "El campo 'email' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        return self._subscribe(user, request.data)

    # Cancela de forma inmediata la membresía activa de un usuario
    @action(detail=False, methods=["post"], url_path="cancel-membership", permission_classes=[IsOperatorAdmin])
    def cancel_membership(self, request):
        serializer = CancelMembershipSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        membership = serializer.membership
        membership.is_active = False
        membership.end_date = timezone.now()
        membership.save(update_fields=["is_active", "end_date"])

        return Response({"detail": "Membresía cancelada de forma inmediata."}, status=status.HTTP_200_OK)

    # Crear una suscripción válida
    def _subscribe(self, user, data):
        serializer = SubscribeSerializer(data=data, context={"user": user})
        if serializer.is_valid():
            membership = serializer.save()
            return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# region Token de refresco
class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer