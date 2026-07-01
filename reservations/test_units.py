from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from reservations.models import Reservation
from reservations.serializers import ReservationCreateSerializer
from users.models import (
    Resource,
    Resource_Type,
)

def _make_resource(price='15.00'):
    rt = Resource_Type.objects.create(name='Sala', description='Sala')
    return Resource.objects.create(
        name='Sala 1',
        capacity=10,
        price=Decimal(price),
        resource_type=rt,
        is_active=True,
        availability=True,
    )


class CalculateTotalPriceTests(TestCase):
    # precio_hora * horas = total de la reserva
    def test_one_hour_at_15_per_hour_costs_15(self):
        resource = _make_resource(price='15.00')
        serializer = ReservationCreateSerializer()
        start = timezone.now()
        end = start + timedelta(hours=1)
        self.assertEqual(serializer._calculate_total_price(resource, start, end), 15.0)

    def test_two_hours_at_15_per_hour_costs_30(self):
        resource = _make_resource(price='15.00')
        serializer = ReservationCreateSerializer()
        start = timezone.now()
        end = start + timedelta(hours=2)
        self.assertEqual(serializer._calculate_total_price(resource, start, end), 30.0)

    def test_half_hour_at_10_per_hour_costs_5(self):
        resource = _make_resource(price='10.00')
        serializer = ReservationCreateSerializer()
        start = timezone.now()
        end = start + timedelta(minutes=30)
        self.assertEqual(serializer._calculate_total_price(resource, start, end), 5.0)

    # Recurso gratuito -> total 0 (la reserva se crea CONFIRMED sin factura)
    def test_free_resource_costs_zero(self):
        resource = _make_resource(price='0')
        serializer = ReservationCreateSerializer()
        start = timezone.now()
        end = start + timedelta(hours=1)
        self.assertEqual(serializer._calculate_total_price(resource, start, end), 0.0)

    # Resultado redondeado a 2 decimales
    def test_rounds_to_two_decimals(self):
        resource = _make_resource(price='7.77')
        serializer = ReservationCreateSerializer()
        start = timezone.now()
        end = start + timedelta(hours=1)
        self.assertEqual(serializer._calculate_total_price(resource, start, end), 7.77)


class GenerateOccurrencesTests(TestCase):
    def setUp(self):
        self.serializer = ReservationCreateSerializer()

    # HOURLY genera exactamente una ocurrencia
    def test_hourly_returns_single_occurrence(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        occ = self.serializer._generate_occurrences(start, end, Reservation.HOURLY, None)
        self.assertEqual(occ, [(start, end)])

    # DAILY genera exactamente una ocurrencia
    def test_daily_returns_single_occurrence(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=8)
        occ = self.serializer._generate_occurrences(start, end, Reservation.DAILY, None)
        self.assertEqual(occ, [(start, end)])

    # WEEKLY genera una ocurrencia por semana hasta la recurrence_end_date
    def test_weekly_one_occurrence_per_week(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        recurrence_end = start + timedelta(weeks=4)
        occ = self.serializer._generate_occurrences(
            start, end, Reservation.WEEKLY, recurrence_end,
        )
        self.assertEqual(len(occ), 5)
        self.assertEqual(occ[1][0] - occ[0][0], timedelta(weeks=1))
        self.assertEqual(occ[2][0] - occ[1][0], timedelta(weeks=1))
        self.assertEqual(occ[4][0] - occ[3][0], timedelta(weeks=1))

    # MONTHLY genera una ocurrencia por mes hasta la recurrence_end_date
    def test_monthly_one_occurrence_per_month(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        recurrence_end = start + timedelta(weeks=12)
        occ = self.serializer._generate_occurrences(
            start, end, Reservation.MONTHLY, recurrence_end,
        )
        # 12 semanas con relativedelta(months=1) caben 3 saltos mensuales
        self.assertEqual(len(occ), 3)

    # Limite maximo: WEEKLY nunca devuelve mas de 52 ocurrencias
    def test_weekly_capped_at_52(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        # 10 años -> claramente por encima del limite
        recurrence_end = start + timedelta(weeks=520)
        occ = self.serializer._generate_occurrences(
            start, end, Reservation.WEEKLY, recurrence_end,
        )
        self.assertEqual(len(occ), 52)

    # Limite maximo: MONTHLY nunca devuelve mas de 12 ocurrencias
    def test_monthly_capped_at_12(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        # 5 años -> claramente por encima del limite
        recurrence_end = start + timedelta(weeks=260)
        occ = self.serializer._generate_occurrences(
            start, end, Reservation.MONTHLY, recurrence_end,
        )
        self.assertEqual(len(occ), 12)

    # El limite <= es inclusivo: la primera ocurre en start y la segunda justo
    # en recurrence_end. La tercera queda fuera y ya no se genera.
    def test_recurrence_stops_at_end_date(self):
        start = timezone.now().replace(microsecond=0)
        end = start + timedelta(hours=1)
        recurrence_end = start + timedelta(weeks=1)
        occ = self.serializer._generate_occurrences(
            start, end, Reservation.WEEKLY, recurrence_end,
        )
        self.assertEqual(len(occ), 2)
