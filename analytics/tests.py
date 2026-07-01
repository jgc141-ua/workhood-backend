from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accesses.models import Access
from invoices_payments.models import Invoice, Payment, PaymentMethod
from reservations.models import Reservation
from users.models import (
    Address,
    CustomUser,
    Legal,
    Membership,
    Membership_Type,
    Resource,
    Resource_Type,
)


def _make_address(street='Calle Mayor 1', city='Madrid', state='Madrid', postal_code='28001', country='España'):
    return Address.objects.create(
        street=street,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
    )


def _make_user(email='user@test.com', role=CustomUser.MIEMBRO, password='Test1234!', address=None, billing_address=None):
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


def _make_resource(name='Sala 1', price='15.00', is_active=True):
    rt, _ = Resource_Type.objects.get_or_create(
        name='Sala',
        defaults={'description': 'Sala de reuniones'},
    )
    return Resource.objects.create(
        name=name,
        capacity=10,
        price=price,
        is_active=is_active,
        resource_type=rt,
    )


def _make_membership(user, membership_type=None):
    if membership_type is None:
        membership_type = Membership_Type.objects.create(
            name='Flex', monthly_price='50.00', is_active=True
        )

    return Membership.objects.create(
        user=user,
        membership_type=membership_type,
        price='50.00',
        end_date=timezone.now() + timedelta(days=10),
        is_active=True,
    )


def _make_checkin(user):
    return Access.objects.create(
        user=user,
        type=Access.ENTRADA,
        result=Access.PERMITIDO,
        user_name=f'{user.first_name} {user.last_name}'.strip(),
        user_email=user.email,
        user_nif_cif=user.nif_cif,
    )

def _make_invoice(user, amount='60.00', state=Invoice.EMITIDA, membership=None):
    from datetime import timedelta as _td
    now = timezone.now()
    invoice = Invoice.objects.create(
        invoice_number=f'INV-2026-{Invoice.objects.count() + 1:06d}',
        concept='Membresía de prueba',
        issuer_name='Workhood Coworking S.L.',
        issuer_nif='B12345678',
        issuer_address='San Vicente del Raspeig, Alicante',
        user=user,
        user_name=f'{user.first_name} {user.last_name}'.strip(),
        user_nif=user.nif_cif or '',
        user_address='Calle prueba 1, Madrid',
        membership=membership,
        tax_base=amount,
        iva_rate='0.21',
        iva_amount=str(round(float(amount) * 0.21, 2)),
        total=str(round(float(amount) * 1.21, 2)),
        due_date=now.replace(hour=23, minute=59, second=59, microsecond=0) - _td(days=0),
        state=state,
    )
    return invoice


def _make_payment_method():
    return PaymentMethod.objects.create(name='Tarjeta', is_active=True, member_visible=True)

class OccupancyCurrentTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.itinerante = _make_user(email='itinerante@test.com', role=CustomUser.MIEMBRO_ITINERANTE)

    # El admin puede consultar un miembro no sin auth tampoco
    def test_permissions(self):
        self.client.force_authenticate(user=self.admin)
        ok = self.client.get(reverse('occupancy_current'))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertIn('count', ok.data)
        self.assertIn('active_checkins', ok.data)

        self.client.force_authenticate(user=self.member)
        forbidden = self.client.get(reverse('occupancy_current'))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=None)
        unauth = self.client.get(reverse('occupancy_current'))
        self.assertEqual(unauth.status_code, status.HTTP_401_UNAUTHORIZED)

    # Check-in activo cuenta check-out lo quita check-in denegado no cuenta
    def test_checkin_states_count_correctly(self):
        _make_checkin(self.member)
        _make_checkin(self.itinerante)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_current'))
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['active_checkins'][0]['user_email'], 'itinerante@test.com')

        Access.objects.create(
            user=self.member,
            type=Access.SALIDA,
            result=Access.PERMITIDO,
            user_name=f'{self.member.first_name} {self.member.last_name}'.strip(),
            user_email=self.member.email,
            user_nif_cif=self.member.nif_cif,
        )
        response = self.client.get(reverse('occupancy_current'))
        self.assertEqual(response.data['count'], 1)

        denied = Access.objects.create(
            user=self.itinerante,
            type=Access.ENTRADA,
            result=Access.DENEGADO,
            user_name=f'{self.itinerante.first_name} {self.itinerante.last_name}'.strip(),
            user_email=self.itinerante.email,
            user_nif_cif=self.itinerante.nif_cif,
        )

        denied.delete()


class ActiveReservationsTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.resource = _make_resource()

    # Solo CONFIRMED en curso aparece PENDING y CANCELLED no
    def test_only_confirmed_in_progress_appears(self):
        now = timezone.now()
        Reservation.objects.create(
            user=self.member, resource=self.resource,
            start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1),
            state=Reservation.CONFIRMED, total_price='15.00',
        )
        Reservation.objects.create(
            user=self.member, resource=self.resource,
            start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1),
            state=Reservation.PENDING, total_price='15.00',
        )
        Reservation.objects.create(
            user=self.member, resource=self.resource,
            start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1),
            state=Reservation.CANCELLED, total_price='15.00',
        )
        Reservation.objects.create(
            user=self.member, resource=self.resource,
            start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=1),
            state=Reservation.CONFIRMED, total_price='15.00',
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_active_reservations'))
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['active_reservations'][0]['resource_name'], 'Sala 1')


class DailyEvolutionTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)

    # Devuelve buckets de 8:00 a 22:00 y los check-ins activos cuentan
    def test_evolution_buckets_and_count(self):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        access = _make_checkin(self.member)
        access.event = now
        access.save()
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_daily_evolution'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['evolution'][0]['hour'], 8)
        self.assertEqual(response.data['evolution'][-1]['hour'], 22)
        bucket = [b for b in response.data['evolution'] if b['hour'] == now.hour][0]
        self.assertEqual(bucket['count'], 1)

    # Fecha con formato inválido devuelve 400
    def test_invalid_date_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_daily_evolution'), {'date': 'invalid'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UsersSummaryTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.itinerante = _make_user(
            email='itinerante@test.com', role=CustomUser.MIEMBRO_ITINERANTE
        )

    # El total excluye al admin y separa por rol
    def test_excludes_admin_and_separates_by_role(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_users_summary'))
        self.assertEqual(response.data['members_total'], 2)
        self.assertEqual(response.data['members_miembro'], 1)
        self.assertEqual(response.data['members_itinerante'], 1)

    # Un miembro no puede consultar el resumen
    def test_member_forbidden(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get(reverse('occupancy_users_summary'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ResourcesSummaryTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.r1 = _make_resource(name='Sala 1', is_active=True)
        self.r2 = _make_resource(name='Sala 2', is_active=True)
        _make_resource(name='Sala 3', is_active=False)

    # El total solo cuenta activos y las reservas CONFIRMED en curso marcan como activos
    def test_active_resources_from_reservations(self):
        now = timezone.now()
        Reservation.objects.create(
            user=self.member, resource=self.r1,
            start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1),
            state=Reservation.CONFIRMED, total_price='15.00',
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('occupancy_resources_summary'))
        # r3 está inactivo, no cuenta en el total
        self.assertEqual(response.data['resources_total'], 2)
        # r1 tiene reserva activa, r2 no
        self.assertEqual(response.data['resources_active'], 1)

class RevenueReportTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.mt = Membership_Type.objects.create(
            name='Premium', monthly_price='100.00', is_active=True
        )
        self.membership = _make_membership(self.member, membership_type=self.mt)
        self.invoice = _make_invoice(self.member, amount='100.00', membership=self.membership)
        Payment.objects.create(
            invoice=self.invoice,
            amount=self.invoice.total,
            method=_make_payment_method(),
            registered_by=self.admin,
        )

    # El admin consulta el miembro no
    def test_permissions(self):
        self.client.force_authenticate(user=self.admin)
        ok = self.client.get(reverse('reports_revenue'))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertIn('facturado', ok.data)
        self.assertIn('cobrado', ok.data)
        self.assertIn('by_membership', ok.data)
        self.assertIn('by_service', ok.data)
        self.assertIn('trend', ok.data)
        self.assertEqual(len(ok.data['trend']), 12)

        self.client.force_authenticate(user=self.member)
        forbidden = self.client.get(reverse('reports_revenue'))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    # Facturado excluye anuladas cobrado suma pagos
    def test_facturado_excludes_anuladas_cobrado_sums_payments(self):
        _make_invoice(self.member, amount='50.00', state=Invoice.ANULADA)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('reports_revenue'), {'period': 'year'})
        # Solo la primera factura de 100€ cuenta
        self.assertEqual(float(response.data['facturado']), 121.0)
        # Pago completo de la primera factura
        self.assertEqual(float(response.data['cobrado']), 121.0)

    # Desglose por membresía agrupa por plan
    def test_by_membership_breakdown(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('reports_revenue'), {'period': 'year'})
        plans = [b['name'] for b in response.data['by_membership']]
        self.assertIn('Premium', plans)

    # Sin reservas no hay by_service con reserva PENDING sí (genera factura en FASE 8)
    def test_by_service_empty_without_reservations(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('reports_revenue'), {'period': 'year'})
        self.assertEqual(response.data['by_service'], [])

    # Período o fecha inválidos devuelven 400
    def test_invalid_params_return_400(self):
        self.client.force_authenticate(user=self.admin)
        bad_period = self.client.get(reverse('reports_revenue'), {'period': 'invalid'})
        self.assertEqual(bad_period.status_code, status.HTTP_400_BAD_REQUEST)
        bad_date = self.client.get(reverse('reports_revenue'), {'date': 'invalid'})
        self.assertEqual(bad_date.status_code, status.HTTP_400_BAD_REQUEST)


class RevenueExportTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.mt = Membership_Type.objects.create(
            name='Premium', monthly_price='100.00', is_active=True
        )
        self.membership = _make_membership(self.member, membership_type=self.mt)
        _make_invoice(self.member, amount='100.00', membership=self.membership)

    # El admin descarga un CSV con los datos
    def test_admin_downloads_csv(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('reports_revenue_export'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv charset=utf-8')
        self.assertIn('attachment', response['Content-Disposition'])
        content = response.content.decode('utf-8-sig')
        self.assertIn('TOTAL', content)
        self.assertIn('Premium', content)
