from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accesses.models import Access
from users.models import (
    Address,
    CustomUser,
    Legal,
    Membership,
    Membership_Type,
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


def _make_membership(user):
    mt = Membership_Type.objects.create(
        name='Flex', monthly_price='50.00', is_active=True
    )
    return Membership.objects.create(
        user=user,
        membership_type=mt,
        price='50.00',
        end_date=timezone.now() + timedelta(days=10),
        is_active=True,
    )


class CheckInTests(APITestCase):
    # Check-in con membresia activa devuelve resultado PERMITIDO
    def test_check_in_with_active_membership_permitido(self):
        user = _make_user(email='user@test.com', role=CustomUser.MIEMBRO)
        _make_membership(user)
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse('access_check_in'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['result'], 'PERMITIDO')
        self.assertEqual(response.data['type'], 'ENTRADA')

    # Check-in sin membresia activa devuelve resultado DENEGADO
    def test_check_in_without_membership_denegado(self):
        user = _make_user(
            email='user@test.com', role=CustomUser.MIEMBRO_ITINERANTE
        )
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse('access_check_in'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['result'], 'DENEGADO')

    # El admin no puede registrar check-in propio
    def test_check_in_admin_rejected(self):
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.post(reverse('access_check_in'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CheckOutTests(APITestCase):
    # Check-out despues de un check-in permitido registra la salida correctamente
    def test_check_out_after_check_in(self):
        user = _make_user(email='user@test.com', role=CustomUser.MIEMBRO)
        _make_membership(user)
        self.client.force_authenticate(user=user)
        self.client.post(reverse('access_check_in'), format='json')
        response = self.client.post(reverse('access_check_out'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'SALIDA')
        self.assertEqual(response.data['result'], 'PERMITIDO')

    # No se puede hacer check-out si no hay un check-in previo
    def test_check_out_without_check_in_fails(self):
        user = _make_user(email='user@test.com', role=CustomUser.MIEMBRO)
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse('access_check_out'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # No se puede hacer check-out si la ultima entrada fue denegada
    def test_check_out_after_denied_check_in_fails(self):
        user = _make_user(
            email='user@test.com', role=CustomUser.MIEMBRO_ITINERANTE
        )
        self.client.force_authenticate(user=user)
        self.client.post(reverse('access_check_in'), format='json')
        response = self.client.post(reverse('access_check_out'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LogsTests(APITestCase):
    # El admin puede listar todos los registros de acceso
    def test_admin_list_logs(self):
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        user = _make_user(email='user@test.com', role=CustomUser.MIEMBRO)
        Access.objects.create(
            user=user,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='Test User',
            user_email='user@test.com',
            user_nif_cif='12345678Z',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.get(reverse('access_logs'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertGreaterEqual(len(results), 1)

    # El listado de logs se puede filtrar por tipo (ENTRADA o SALIDA)
    def test_logs_filter_by_type(self):
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        user = _make_user(email='user@test.com', role=CustomUser.MIEMBRO)
        Access.objects.create(
            user=user,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='Test User',
            user_email='user@test.com',
            user_nif_cif='12345678Z',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.get(reverse('access_logs'), {'type': 'ENTRADA'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        for r in results:
            self.assertEqual(r['type'], 'ENTRADA')

    # El endpoint my-logs solo devuelve los registros del usuario autenticado
    def test_my_logs_returns_only_own(self):
        user1 = _make_user(email='user1@test.com', role=CustomUser.MIEMBRO)
        user2 = _make_user(email='user2@test.com', role=CustomUser.MIEMBRO)
        Access.objects.create(
            user=user1,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='Test User',
            user_email='user1@test.com',
            user_nif_cif='12345678Z',
        )
        Access.objects.create(
            user=user2,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='Test User',
            user_email='user2@test.com',
            user_nif_cif='12345678Z',
        )
        self.client.force_authenticate(user=user1)
        response = self.client.get(reverse('access_my_logs'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        for r in results:
            self.assertEqual(r['user_email'], 'user1@test.com')
