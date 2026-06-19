from django.db.models import ProtectedError, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.pagination import Pagination
from users.permissions import IsOperatorAdmin

from .models import Invoice, PaymentMethod
from .serializers import (
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    IssueInvoiceSerializer,
    PayInvoiceSerializer,
    PaymentMethodSerializer,
    RegisterPaymentSerializer,
)


# region PaymentMethod
class PaymentMethodsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentMethod.objects.all()

    @action(detail=False, methods=['get'], url_path='all', permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by('name')
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='create', permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = PaymentMethodSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['put', 'patch'], url_path='update', permission_classes=[IsOperatorAdmin])
    def update(self, request):
        name = request.data.get('name')
        if not name:
            return Response(
                {'detail': "El campo 'name' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_method = PaymentMethod.objects.get(name=name)
        except PaymentMethod.DoesNotExist:
            return Response(
                {'detail': 'Método de pago no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PaymentMethodSerializer(payment_method, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['delete'], url_path='delete', permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        name = request.data.get('name')
        if not name:
            return Response(
                {'detail': "El campo 'name' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_method = PaymentMethod.objects.get(name=name)
        except PaymentMethod.DoesNotExist:
            return Response(
                {'detail': 'Método de pago no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payment_method.delete()
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar el método de pago porque tiene pagos asociados.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {'detail': 'Método de pago eliminado correctamente.'},
            status=status.HTTP_204_NO_CONTENT,
        )


# region Invoices (Miembro)
class InvoicesMemberViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_owned_invoice(self, request, pk):
        try:
            return Invoice.objects.get(pk=pk, user=request.user)
        except Invoice.DoesNotExist:
            return None

    @action(detail=False, methods=['get'], url_path='my')
    def my(self, request):
        queryset = Invoice.objects.filter(user=request.user).order_by('-issue_date')

        state = request.query_params.get('state')
        if state:
            queryset = queryset.filter(state=state)

        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-detail')
    def my_detail(self, request):
        pk = request.query_params.get('id')
        if not pk:
            return Response(
                {'detail': "El parámetro 'id' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = self._get_owned_invoice(request, pk)
        if not invoice:
            return Response(
                {'detail': 'Factura no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = InvoiceDetailSerializer(invoice)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='pay')
    def pay(self, request):
        pk = request.data.get('id')
        if not pk:
            return Response(
                {'detail': "El campo 'id' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = self._get_owned_invoice(request, pk)
        if not invoice:
            return Response(
                {'detail': 'Factura no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PayInvoiceSerializer(
            data=request.data,
            context={'invoice': invoice, 'registered_by': request.user},
        )
        if serializer.is_valid():
            payment = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# region Invoices (Operador)
class InvoicesAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsOperatorAdmin]

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        queryset = Invoice.objects.all().order_by('-issue_date')

        state = request.query_params.get('state')
        email = request.query_params.get('email')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if state:
            queryset = queryset.filter(state=state)
        if email:
            queryset = queryset.filter(user__email__icontains=email)
        if date_from:
            queryset = queryset.filter(issue_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(issue_date__date__lte=date_to)

        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='invoice-detail')
    def invoice_detail(self, request):
        pk = request.query_params.get('id')
        if not pk:
            return Response(
                {'detail': "El parámetro 'id' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response(
                {'detail': 'Factura no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = InvoiceDetailSerializer(invoice)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='issue')
    def issue(self, request):
        serializer = IssueInvoiceSerializer(data=request.data)
        if serializer.is_valid():
            invoice = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='register-payment')
    def register_payment(self, request):
        serializer = RegisterPaymentSerializer(
            data=request.data,
            context={'registered_by': request.user},
        )
        if serializer.is_valid():
            payment = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
