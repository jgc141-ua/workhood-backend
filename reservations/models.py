from django.db import models

from users.models import CustomUser, Membership, Resource


# region SpaceSchedule
class SpaceSchedule(models.Model):
    id = models.AutoField(primary_key=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    is_open = models.BooleanField(default=True)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# region Reservation
class Reservation(models.Model):
    id = models.AutoField(primary_key=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    HOURLY = 'HOURLY'
    DAILY = 'DAILY'
    WEEKLY = 'WEEKLY'
    MONTHLY = 'MONTHLY'
    RESERVATION_TYPE_CHOICES = [
        (HOURLY, 'Por horas'),
        (DAILY, 'Día completo'),
        (WEEKLY, 'Semanal'),
        (MONTHLY, 'Mensual'),
    ]

    reservation_type = models.CharField(max_length=20, choices=RESERVATION_TYPE_CHOICES, default=HOURLY)

    PENDING = 'Pending'
    CONFIRMED = 'Confirmed'
    CANCELLED = 'Cancelled'
    STATE_CHOICES = [
        (PENDING, 'Pendiente'),
        (CONFIRMED, 'Confirmada'),
        (CANCELLED, 'Cancelada'),
    ]

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=PENDING)
    recurrence_end_date = models.DateTimeField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Relaciones
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='reservations')
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='reservations')
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name='reservations', null=True, blank=True)
    invoice = models.ForeignKey('invoices_payments.Invoice', on_delete=models.SET_NULL, related_name='reservations', null=True, blank=True)
