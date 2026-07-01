from django.conf import settings
from django.db import models

from users.managers import SoftDeleteManager, SoftDeleteModel
from users.models import CustomUser, Membership


# region PaymentMethod
class PaymentMethod(SoftDeleteModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    member_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(deleted_at__isnull=True),
                name='unique_active_payment_method_name',
            ),
        ]
        base_manager_name = 'all_objects'

    objects = SoftDeleteManager()
    all_objects = models.Manager()


# region Invoice
class Invoice(models.Model):
    EMITIDA = 'EMITIDA'
    PAGADA = 'PAGADA'
    VENCIDA = 'VENCIDA'
    ANULADA = 'ANULADA'
    STATE_CHOICES = [
        (EMITIDA, 'Emitida'),
        (PAGADA, 'Pagada'),
        (VENCIDA, 'Vencida'),
        (ANULADA, 'Anulada'),
    ]

    id = models.AutoField(primary_key=True)
    invoice_number = models.CharField(max_length=20, unique=True)
    concept = models.CharField(max_length=255)

    # Datos fiscales del emisor
    issuer_name = models.CharField(max_length=255)
    issuer_nif = models.CharField(max_length=20)
    issuer_address = models.CharField(max_length=500)

    # Datos fiscales del receptor
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='invoices')
    user_name = models.CharField(max_length=255)
    user_nif = models.CharField(max_length=20)
    user_address = models.CharField(max_length=500)

    # Relaciones opcionales
    membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name='invoices',
        null=True,
        blank=True,
    )

    # Importes
    tax_base = models.DecimalField(max_digits=10, decimal_places=2)
    iva_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=settings.IVA_DEFAULT_RATE
    )
    iva_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # Fechas
    issue_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Estado
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=EMITIDA)
    cancelled_reason = models.CharField(max_length=255, blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)


# region InvoiceItem
class InvoiceItem(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)


# region Payment
class Payment(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name='payments'
    )
    payment_date = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    registered_by = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='registered_payments',
        null=True,
        blank=True,
    )
