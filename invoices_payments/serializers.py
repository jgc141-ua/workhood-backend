from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from users.models import CustomUser

from .models import Invoice, InvoiceItem, Payment, PaymentMethod


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
            'created_at',
            'updated_at',
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'is_active': {'required': False},
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

    def _generate_invoice_number(self):
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

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data['email']
        concept = validated_data['concept']
        amount = Decimal(str(validated_data['amount']))
        iva_rate = Decimal(str(validated_data.get('iva_rate', settings.IVA_DEFAULT_RATE)))

        iva_amount = (amount * iva_rate).quantize(Decimal('0.01'))
        total = (amount + iva_amount).quantize(Decimal('0.01'))

        user = CustomUser.objects.get(email=email)

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
        now = timezone.now()

        invoice = Invoice.objects.create(
            invoice_number=self._generate_invoice_number(),
            concept=concept,
            issuer_name=issuer['name'],
            issuer_nif=issuer['nif'],
            issuer_address=issuer['address'],
            user=user,
            user_name=f'{user.first_name} {user.last_name}'.strip(),
            user_nif=user.nif_cif or '',
            user_address=user_address,
            tax_base=amount,
            iva_rate=iva_rate,
            iva_amount=iva_amount,
            total=total,
            due_date=now + timedelta(days=7),
            period_start=now.date(),
            period_end=(now + timedelta(days=30)).date(),
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

    def to_representation(self, instance):
        return InvoiceDetailSerializer(instance, context=self.context).data
