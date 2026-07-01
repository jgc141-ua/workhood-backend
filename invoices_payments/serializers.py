from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from rest_framework import serializers

from users.models import CustomUser

from .models import Invoice, InvoiceItem, Payment, PaymentMethod
from reservations.models import Reservation
from users.models import CustomUser, Membership


# Registra un pago sobre una factura y marca PAGADA si cubre el total
# Si la factura tiene reservas vinculadas, las confirma
@transaction.atomic
def register_payment(invoice, amount, method, registered_by=None, reference=None):
    amount = Decimal(str(amount))
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        registered_by=registered_by,
        reference=reference,
    )

    total_paid = invoice.payments.aggregate(
        total=models.Sum('amount')
    )['total'] or Decimal('0')

    if invoice.state in (Invoice.EMITIDA, Invoice.VENCIDA) and total_paid >= invoice.total:
        invoice.state = Invoice.PAGADA
        invoice.save(update_fields=['state', 'updated_at'])

        # Confirmar reservas vinculadas a esta factura
        for reservation in invoice.reservations.all():
            if reservation.state == 'Pending':
                reservation.state = 'Confirmed'
                reservation.save(update_fields=['state'])

    return payment


# region PaymentMethod
class PaymentMethodSerializer(serializers.ModelSerializer):
    new_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = PaymentMethod
        fields = (
            'id',
            'name',
            'new_name',
            'is_active',
            'member_visible',
            'created_at',
            'updated_at',
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'is_active': {'required': False},
            'member_visible': {'required': False},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
        }

    def validate(self, data):
        name = data.get('name')
        new_name = data.get('new_name')

        if new_name:
            if PaymentMethod.objects.filter(name=new_name).exclude(name=name).exists():
                raise serializers.ValidationError(
                    {'new_name': 'Ya existe un método de pago con ese nombre.'}
                )

        return data

    def update(self, instance, validated_data):
        new_name = validated_data.pop('new_name', None)
        if new_name:
            validated_data.pop('name', None)
            instance.name = new_name
        return super().update(instance, validated_data)


# region InvoiceItem
class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ('id', 'description', 'quantity', 'unit_price', 'subtotal')
        extra_kwargs = {
            'id': {'read_only': True},
        }


# region Payment
class PaymentSerializer(serializers.ModelSerializer):
    method_name = serializers.CharField(source='method.name', read_only=True)
    registered_by_email = serializers.CharField(source='registered_by.email', read_only=True, default='Sistema')

    class Meta:
        model = Payment
        fields = (
            'id',
            'amount',
            'method',
            'method_name',
            'payment_date',
            'reference',
            'registered_by',
            'registered_by_email',
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'payment_date': {'read_only': True},
            'registered_by': {'read_only': True},
        }


# region Invoice (listado)
class InvoiceListSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name_full = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            'id',
            'invoice_number',
            'concept',
            'user_email',
            'user_name_full',
            'total',
            'issue_date',
            'due_date',
            'period_start',
            'period_end',
            'state',
            'membership',
        )
        extra_kwargs = {
            'id': {'read_only': True},
        }

    def get_user_name_full(self, obj):
        return f"{obj.user_name}".strip()


# region Invoice (detalle)
class InvoiceDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = (
            'id',
            'invoice_number',
            'concept',
            'issuer_name',
            'issuer_nif',
            'issuer_address',
            'user',
            'user_email',
            'user_name',
            'user_nif',
            'user_address',
            'membership',
            'tax_base',
            'iva_rate',
            'iva_amount',
            'total',
            'issue_date',
            'due_date',
            'period_start',
            'period_end',
            'state',
            'cancelled_reason',
            'updated_at',
            'items',
            'payments',
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'user': {'read_only': True},
        }


# region IssueInvoice
class IssueInvoiceSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    concept = serializers.CharField(max_length=255, required=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    iva_rate = serializers.DecimalField(
        max_digits=5, decimal_places=4, required=False, default=settings.IVA_DEFAULT_RATE
    )

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError('Usuario no encontrado.')
        return value

    def create(self, validated_data):
        user = CustomUser.objects.get(email=validated_data['email'])
        return _create_invoice(
            user=user,
            concept=validated_data['concept'],
            amount=validated_data['amount'],
            iva_rate=validated_data.get('iva_rate'),
        )

    def to_representation(self, instance):
        return InvoiceDetailSerializer(instance, context=self.context).data


# Genera un número de factura secuencial anual: INV-YYYY-NNNNNN
def _generate_invoice_number():
    year = timezone.now().year
    prefix = f'INV-{year}-'
    last = (
        Invoice.objects
        .filter(invoice_number__startswith=prefix)
        .order_by('-invoice_number')
        .first()
    )
    if last:
        try:
            seq = int(last.invoice_number.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:06d}'


# Crea una factura EMITIDA con su línea de detalle
@transaction.atomic
def _create_invoice(
    user,
    concept,
    amount,
    iva_rate=None,
    membership=None,
    period_start=None,
    period_end=None,
    due_date=None,
):
    if iva_rate is None:
        iva_rate = settings.IVA_DEFAULT_RATE

    amount = Decimal(str(amount))
    iva_rate = Decimal(str(iva_rate))
    iva_amount = (amount * iva_rate).quantize(Decimal('0.01'))
    total = (amount + iva_amount).quantize(Decimal('0.01'))

    if due_date is None:
        due_date = timezone.now() + timedelta(days=7)

    user_address = ''
    if user.address:
        parts = [
            user.address.street,
            user.address.city,
            user.address.state,
            user.address.postal_code,
            user.address.country,
        ]
        user_address = ', '.join(p for p in parts if p)

    issuer = settings.ISSUER_DATA

    invoice = Invoice.objects.create(
        invoice_number=_generate_invoice_number(),
        concept=concept,
        issuer_name=issuer['name'],
        issuer_nif=issuer['nif'],
        issuer_address=issuer['address'],
        user=user,
        user_name=f'{user.first_name} {user.last_name}'.strip(),
        user_nif=user.nif_cif or '',
        user_address=user_address,
        membership=membership,
        tax_base=amount,
        iva_rate=iva_rate,
        iva_amount=iva_amount,
        total=total,
        due_date=due_date,
        period_start=period_start,
        period_end=period_end,
        state=Invoice.EMITIDA,
    )

    InvoiceItem.objects.create(
        invoice=invoice,
        description=concept,
        quantity=Decimal('1'),
        unit_price=amount,
        subtotal=amount,
    )

    return invoice


# Genera una factura EMITIDA a partir de una membresía recién creada
def generate_membership_invoice(membership):
    membership_type = membership.membership_type
    now = timezone.now()
    due_date = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return _create_invoice(
        user=membership.user,
        concept=f'Membresía {membership_type.name} ({membership.start_date.date().strftime('%d-%m-%Y')} a {membership.end_date.date().strftime('%d-%m-%Y')})',
        amount=membership_type.monthly_price,
        membership=membership,
        period_start=membership.start_date.date(),
        period_end=membership.end_date.date(),
        due_date=due_date,
    )


# region PayInvoice
class PayInvoiceSerializer(serializers.Serializer):
    method = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all())
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_method(self, value):
        if not value.is_active:
            raise serializers.ValidationError('El método de pago no está activo.')
        return value

    def validate(self, data):
        invoice = self.context.get('invoice')
        if not invoice:
            raise serializers.ValidationError('Falta la factura en el contexto.')

        if invoice.state not in (Invoice.EMITIDA, Invoice.VENCIDA):
            raise serializers.ValidationError(
                'La factura no admite pagos en su estado actual.'
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        invoice = self.context['invoice']
        registered_by = self.context.get('registered_by')

        payment = register_payment(
            invoice=invoice,
            amount=invoice.total,
            method=validated_data['method'],
            registered_by=registered_by,
            reference=validated_data.get('reference'),
        )

        return payment

    def to_representation(self, instance):
        return PaymentSerializer(instance).data


# region RegisterPayment (admin)
class RegisterPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    method = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all())
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_method(self, value):
        if not value.is_active:
            raise serializers.ValidationError('El método de pago no está activo.')
        return value

    def validate(self, data):
        try:
            invoice = Invoice.objects.get(pk=data['id'])
        except Invoice.DoesNotExist:
            raise serializers.ValidationError({'id': 'Factura no encontrada.'})

        if invoice.state not in (Invoice.EMITIDA, Invoice.VENCIDA):
            raise serializers.ValidationError(
                'La factura no admite pagos en su estado actual.'
            )

        self._invoice = invoice
        return data

    @transaction.atomic
    def create(self, validated_data):
        registered_by = self.context.get('registered_by')

        payment = register_payment(
            invoice=self._invoice,
            amount=self._invoice.total,
            method=validated_data['method'],
            registered_by=registered_by,
            reference=validated_data.get('reference'),
        )

        return payment

    def to_representation(self, instance):
        return PaymentSerializer(instance).data


# region CancelInvoice
class CancelInvoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    reason = serializers.CharField(max_length=255, required=True)

    def validate(self, data):
        try:
            invoice = Invoice.objects.get(pk=data['id'])
        except Invoice.DoesNotExist:
            raise serializers.ValidationError({'id': 'Factura no encontrada.'})

        if invoice.state == Invoice.ANULADA:
            raise serializers.ValidationError('La factura ya está anulada.')

        if invoice.state == Invoice.PAGADA:
            raise serializers.ValidationError('No se puede anular una factura pagada.')

        self._invoice = invoice
        return data

    def save(self):
        invoice = self._invoice
        invoice.state = Invoice.ANULADA
        invoice.cancelled_reason = self.validated_data['reason']
        invoice.save(update_fields=['state', 'cancelled_reason', 'updated_at'])

        # Si la factura tiene membresía vinculada, cancelarla
        if invoice.membership:
            invoice.membership.is_active = False
            invoice.membership.end_date = timezone.now()
            invoice.membership.save(update_fields=['is_active', 'end_date'])

            invoice.membership.user.role = 'MIEMBRO_ITINERANTE'
            invoice.membership.user.save(update_fields=['role'])

        return invoice

    def to_representation(self, instance):
        return InvoiceDetailSerializer(instance).data

# region Facturas vencidas
# Marca como VENCIDA las facturas EMITIDA con due_date < hoy
# Cancela las reservas vinculadas a facturas que pasan a VENCIDA
@transaction.atomic
def _mark_overdue_invoices_bulk():
    now = timezone.now()

    # IDs de facturas que pasan a VENCIDA
    overdue_ids = list(
        Invoice.objects.filter(
            state=Invoice.EMITIDA,
            due_date__lt=now,
        ).values_list('id', flat=True)
    )
    if not overdue_ids:
        return

    # Facturas
    Invoice.objects.filter(id__in=overdue_ids).update(
        state=Invoice.VENCIDA,
        updated_at=now,
    )

    # Rservas
    Reservation.objects.filter(
        invoice__id__in=overdue_ids
    ).exclude(state='Cancelled').update(state='Cancelled')

    # Membresías
    membership_ids = list(
        Invoice.objects.filter(id__in=overdue_ids)
        .exclude(membership__isnull=True)
        .values_list('membership_id', flat=True)
        .distinct()
    )
    if membership_ids:
        Membership.objects.filter(id__in=membership_ids).update(
            is_active=False,
            end_date=now,
        )
        # Roles
        CustomUser.objects.filter(
            user_membership__id__in=membership_ids
        ).update(role=CustomUser.MIEMBRO_ITINERANTE)

# region Renovación
# Renueva membresías con auto_renew=True cuyo end_date ya ha pasado
# Crea nueva membresía + factura. No duplica si ya se renovó
@transaction.atomic
def _process_renewals_bulk():
    now = timezone.now()

    expired = list(
        Membership.objects.filter(
            is_active=True,
            auto_renew=True,
            end_date__lte=now,
        ).select_related('user', 'membership_type', 'resource')
    )

    if not expired:
        return

    expired_ids = [m.id for m in expired]

    # IDs de membresías que YA tienen una membresía posterior (ya renovadas)
    already_renewed_ids = set(
        Membership.objects.filter(
            user__in=[m.user_id for m in expired],
            start_date__gt=models.F('user__user_membership__end_date'),
        ).exclude(
            id__in=expired_ids,
        ).values_list('id', flat=True)
    )

    # Marcar TODAS las expiradas como inactivas de una vez
    Membership.objects.filter(id__in=expired_ids).update(is_active=False)

    # Solo crear nuevas para las que no tienen renovación previa
    new_memberships = []
    for membership in expired:
        if membership.id in already_renewed_ids:
            continue

        new_memberships.append(Membership(
            user=membership.user,
            membership_type=membership.membership_type,
            resource=membership.resource,
            price=membership.membership_type.monthly_price,
            start_date=now,
            end_date=now + timedelta(days=30),
            is_active=True,
            auto_renew=True,
        ))

    # Crear todas las membresías nuevas en una sola query
    created = Membership.objects.bulk_create(new_memberships)

    # Generar facturas para cada nueva membresía
    for new_membership in created:
        generate_membership_invoice(new_membership)

# Procesar facturas y renovaciones
def process_pending_invoices():
    _mark_overdue_invoices_bulk()
    _process_renewals_bulk()