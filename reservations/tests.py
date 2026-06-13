from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from reservations.models import Reservation, SpaceSchedule
from users.models import (
    Address,
    CustomUser,
    Legal,
    Membership,
    Membership_Type,
    Resource,
    Resource_Type,
)


def _make_address(
    street='Calle Mayor 1',
    city='Madrid',
    state='Madrid',
    postal_code='28001',
    country='España',
):
    return Address.objects.create(
        street=street,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
    )


def _make_user(
    email='user@test.com',
    role=CustomUser.MIEMBRO,
    password='Test1234!',
    address=None,
    billing_address=None,
):
    if address is None:
        address = _make_address()
    if billing_address is None:
        billing_address = address
    user = CustomUser(
        email=email,
        first_name='Test',
        last_name='User',
        nif_cif='12345678Z',
        phone='+34 600000000',
        role=role,
        address=address,
        billing_address=billing_address,
    )
    user.set_password(password)
    user.save()
    Legal.objects.create(user=user, terms=True, privacy=True, marketing=False)
    return user


def _make_membership(user, mt=None):
    if mt is None:
        mt, _ = Membership_Type.objects.get_or_create(
            name='Flex',
            defaults={'monthly_price': '50.00', 'is_active': True},
        )
    return Membership.objects.create(
        user=user,
        membership_type=mt,
        price=mt.monthly_price,
        end_date=timezone.now() + timedelta(days=30),
        is_active=True,
    )


def _make_resource(name='Sala 1', capacity=10, price='15.00', rt=None):
    if rt is None:
        rt = Resource_Type.objects.create(name='Sala', description='Sala')
    return Resource.objects.create(
        name=name,
        description='Sala de reuniones',
        capacity=capacity,
        price=price,
        availability=True,
        is_active=True,
        resource_type=rt,
    )


def _make_schedule(opening='09:00', closing='18:00'):
    from datetime import date

    return SpaceSchedule.objects.create(
        start_date=date(2026, 1, 1),
        end_date=None,
        opening_time=opening,
        closing_time=closing,
        is_open=True,
    )


class ReservationCreateTests(APITestCase):
    def setUp(self):
        self.user = _make_user(email='user@test.com')
        _make_membership(self.user)
        self.resource = _make_resource()
        _make_schedule()
        self.client.force_authenticate(user=self.user)

    def _future_slot(self, hour=10):
        start = (timezone.now() + timedelta(days=1)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        return start, start + timedelta(hours=1)

    # Crea una reserva por horas en el futuro correctamente
    def test_create_hourly_reservation(self):
        start, end = self._future_slot(10)
        data = {
            'resource': self.resource.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reservation_type': 'HOURLY',
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Reservation.objects.filter(user=self.user, resource=self.resource).exists()
        )

    # No se puede crear una reserva en el pasado
    def test_create_in_past_fails(self):
        start = (timezone.now() - timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        data = {
            'resource': self.resource.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reservation_type': 'HOURLY',
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # No se puede crear una reserva que se solape con otra existente
    def test_overlapping_reservation_fails(self):
        start, end = self._future_slot(10)
        Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=start,
            end_time=end,
            reservation_type='HOURLY',
            state='Confirmed',
        )
        data = {
            'resource': self.resource.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reservation_type': 'HOURLY',
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Crea una reserva de dia completo ajustada al horario del espacio
    def test_create_daily_reservation(self):
        target = (timezone.now() + timedelta(days=2)).date()
        data = {
            'resource': self.resource.id,
            'start_time': f'{target}T00:00',
            'end_time': f'{target}T23:59',
            'reservation_type': 'DAILY',
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # Una reserva WEEKLY genera multiples ocurrencias hasta recurrence_end_date
    def test_weekly_recurrence_generates_multiple(self):
        start, end = self._future_slot(10)
        data = {
            'resource': self.resource.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reservation_type': 'WEEKLY',
            'recurrence_end_date': (start + timedelta(weeks=4)).isoformat(),
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(
            Reservation.objects.filter(user=self.user, resource=self.resource).count(),
            2,
        )

    # Una reserva MONTHLY genera multiples ocurrencias hasta recurrence_end_date
    def test_monthly_recurrence_generates_multiple(self):
        start, end = self._future_slot(10)
        data = {
            'resource': self.resource.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reservation_type': 'MONTHLY',
            'recurrence_end_date': (start + timedelta(weeks=12)).isoformat(),
        }
        response = self.client.post(reverse('create_reservation'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(
            Reservation.objects.filter(user=self.user, resource=self.resource).count(),
            2,
        )


class ReservationCancelTests(APITestCase):
    def setUp(self):
        self.user = _make_user(email='user@test.com')
        _make_membership(self.user)
        self.resource = _make_resource()
        _make_schedule()
        self.start = (timezone.now() + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        self.reservation = Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.start,
            end_time=self.start + timedelta(hours=1),
            reservation_type='HOURLY',
            state='Confirmed',
        )
        self.client.force_authenticate(user=self.user)

    # Un miembro puede cancelar su propia reserva futura
    def test_cancel_own_reservation(self):
        response = self.client.post(
            reverse('cancel_reservation'), {'id': self.reservation.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.state, 'Cancelled')

    # Un miembro no puede cancelar la reserva de otro miembro
    def test_cannot_cancel_others_reservation(self):
        other = _make_user(email='other@test.com')
        _make_membership(other)
        self.client.force_authenticate(user=other)
        response = self.client.post(
            reverse('cancel_reservation'), {'id': self.reservation.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # El admin puede cancelar la reserva de cualquier miembro
    def test_admin_can_cancel_any(self):
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            reverse('cancel_reservation'), {'id': self.reservation.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AvailabilityTests(APITestCase):
    def setUp(self):
        self.user = _make_user(email='user@test.com')
        _make_membership(self.user)
        self.resource = _make_resource()
        _make_schedule()
        self.client.force_authenticate(user=self.user)

    # El endpoint de availability devuelve true cuando el slot esta libre
    def test_availability_returns_free(self):
        start = (timezone.now() + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        response = self.client.get(
            reverse('availability'),
            {
                'resource': self.resource.id,
                'start_time': start.isoformat(),
                'end_time': end.isoformat(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['available'])

    # El endpoint de availability devuelve false cuando el slot esta ocupado
    def test_availability_returns_occupied(self):
        start = (timezone.now() + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=start,
            end_time=end,
            reservation_type='HOURLY',
            state='Confirmed',
        )
        response = self.client.get(
            reverse('availability'),
            {
                'resource': self.resource.id,
                'start_time': start.isoformat(),
                'end_time': end.isoformat(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['available'])

    # Devuelve los bloques de horario del recurso con huecos libres y ocupados
    def test_resource_schedule_returns_blocks(self):
        target = (timezone.now() + timedelta(days=1)).date()
        response = self.client.get(
            reverse('resource_schedule'),
            {'resource': self.resource.id, 'date': target.isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_open'])
        self.assertIn('blocks', response.data)


class ReservationListTests(APITestCase):
    def setUp(self):
        self.user = _make_user(email='user@test.com')
        _make_membership(self.user)
        self.resource = _make_resource()
        _make_schedule()
        self.start = (timezone.now() + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.start,
            end_time=self.start + timedelta(hours=1),
            reservation_type='HOURLY',
            state='Confirmed',
        )
        self.client.force_authenticate(user=self.user)

    # Lista las reservas del usuario autenticado
    def test_list_my_reservations(self):
        response = self.client.get(reverse('my_reservations'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertGreaterEqual(len(results), 1)

    # El admin puede listar todas las reservas del sistema
    def test_admin_list_all_reservations(self):
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.get(reverse('all_reservations'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
