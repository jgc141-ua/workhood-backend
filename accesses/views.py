from django.db import models
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.pagination import Pagination
from users.models import CustomUser, Membership
from users.permissions import IsOperatorAdmin

from .models import Access
from .serializers import AccessSerializer

# region Access
class AccessViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # Busca la membresía activa más reciente del usuario
    def _get_active_membership(self, user):
        return (
            Membership.objects.filter(
                user=user,
                is_active=True,
                end_date__gte=timezone.now(),
            )
            .select_related("membership_type", "resource")
            .order_by("-start_date")
            .first()
        )

    # Busca el último acceso registrado por el usuario
    def _get_last_access(self, user):
        return Access.objects.filter(user=user).order_by("-event").first()

    # Crea un registro de acceso con los datos actuales del usuario
    def _create_access(self, user, access_type, result, membership=None):
        access = Access.objects.create(
            type=access_type,
            result=result,
            user=user,
            user_name=f"{user.first_name} {user.last_name}".strip(),
            user_email=user.email,
            user_nif_cif=user.nif_cif,
            membership=membership,
        )
        return access

    # Registra la entrada de un miembro y valida su membresía
    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        user = request.user

        # Los operadores no registran entradas ni salidas
        if user.role == CustomUser.ADMIN:
            return Response(
                {"detail": "Los operadores no registran accesos de entrada/salida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verifica si el usuario tiene facturas de membresía vencidas impagadas
        from invoices_payments.models import Invoice
        has_overdue = Invoice.objects.filter(
            user=user,
            state=Invoice.VENCIDA,
            membership__isnull=False,
        ).exists()

        if has_overdue:
            access = self._create_access(
                user,
                Access.ENTRADA,
                Access.DENEGADO,
            )
            return Response(
                {"detail": "Acceso denegado. Tienes facturas vencidas pendientes de pago."},
                status=status.HTTP_403_FORBIDDEN,
            )

        membership = self._get_active_membership(user)

        if membership:
            access = self._create_access(
                user,
                Access.ENTRADA,
                Access.PERMITIDO,
                membership=membership,
            )
        else:
            access = self._create_access(
                user,
                Access.ENTRADA,
                Access.DENEGADO,
            )

        return Response(AccessSerializer(access).data, status=status.HTTP_201_CREATED)

    # Registra la salida de un miembro
    @action(detail=False, methods=["post"], url_path="check-out")
    def check_out(self, request):
        user = request.user

        # Los operadores no registran entradas ni salidas
        if user.role == CustomUser.ADMIN:
            return Response(
                {"detail": "Los operadores no registran accesos de entrada/salida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        last_access = self._get_last_access(user)

        # No se puede registrar salida sin una entrada previa
        if not last_access or last_access.type == Access.SALIDA:
            return Response(
                {"detail": "No hay una entrada previa para registrar la salida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # No se puede registrar salida si la última entrada fue denegada
        if last_access.result == Access.DENEGADO:
            return Response(
                {"detail": "La última entrada fue denegada, no se puede registrar la salida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        access = self._create_access(
            user,
            Access.SALIDA,
            Access.PERMITIDO,
        )

        return Response(AccessSerializer(access).data, status=status.HTTP_201_CREATED)

    # Listado paginado de accesos para el operador, con filtros opcionales
    @action(detail=False, methods=["get"], url_path="logs", permission_classes=[IsOperatorAdmin])
    def logs(self, request):
        queryset = Access.objects.select_related(
            "user",
            "membership",
            "membership__membership_type",
            "membership__resource",
        ).order_by("-event")

        access_type = request.query_params.get("type")
        access_result = request.query_params.get("result")
        user_email = request.query_params.get("email")

        if access_type:
            queryset = queryset.filter(type=access_type.upper())
        if access_result:
            queryset = queryset.filter(result=access_result.upper())
        if user_email:
            queryset = queryset.filter(
                models.Q(user__email__icontains=user_email) |
                models.Q(user_email__icontains=user_email)
            )

        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AccessSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Listado paginado de los accesos del usuario autenticado
    @action(detail=False, methods=["get"], url_path="my-logs")
    def my_logs(self, request):
        queryset = Access.objects.filter(user=request.user).select_related(
            "membership",
            "membership__membership_type",
            "membership__resource",
        ).order_by("-event")

        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AccessSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
