from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import Address, CustomUser, Legal

from invoices_payments.models import PaymentMethod


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
    first_name='Test',
    last_name='User',
    address=None,
    billing_address=None,
):
    if address is None:
        address = _make_address()
    if billing_address is None:
        billing_address = address
    user = CustomUser(
        email=email,
        first_name=first_name,
        last_name=last_name,
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


class PaymentMethodListTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        PaymentMethod.objects.create(name='Tarjeta', is_active=True)
        PaymentMethod.objects.create(name='Transferencia', is_active=True)
        PaymentMethod.objects.create(name='Efectivo', is_active=False)

    # El admin lista todos los métodos de pago
    def test_list_all_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('all_payment_methods'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [pm['name'] for pm in response.data]
        self.assertIn('Tarjeta', names)
        self.assertIn('Transferencia', names)
        self.assertIn('Efectivo', names)

    # Un miembro no puede listar los métodos de pago
    def test_list_all_as_member_forbidden(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get(reverse('all_payment_methods'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # Un usuario no autenticado no puede listar los métodos de pago
    def test_list_all_unauthenticated_forbidden(self):
        response = self.client.get(reverse('all_payment_methods'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PaymentMethodCreateTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)

    # El admin crea un nuevo método de pago
    def test_create_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Tarjeta', 'is_active': True}
        response = self.client.post(reverse('create_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PaymentMethod.objects.filter(name='Tarjeta').exists())

    # No se puede crear un método de pago con un nombre ya existente activo
    def test_create_duplicate_name_fails(self):
        PaymentMethod.objects.create(name='Tarjeta', is_active=True)
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Tarjeta', 'is_active': True}
        response = self.client.post(reverse('create_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Un miembro no puede crear métodos de pago
    def test_create_as_member_forbidden(self):
        self.client.force_authenticate(user=self.member)
        data = {'name': 'Tarjeta', 'is_active': True}
        response = self.client.post(reverse('create_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PaymentMethodUpdateTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.pm = PaymentMethod.objects.create(name='Tarjeta', is_active=True)

    # El admin actualiza un método de pago
    def test_update_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Tarjeta', 'is_active': False}
        response = self.client.patch(reverse('update_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pm.refresh_from_db()
        self.assertFalse(self.pm.is_active)

    # El admin puede renombrar un método de pago usando new_name
    def test_rename_with_new_name(self):
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Tarjeta', 'new_name': 'Tarjeta bancaria'}
        response = self.client.patch(reverse('update_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pm.refresh_from_db()
        self.assertEqual(self.pm.name, 'Tarjeta bancaria')

    # No se puede renombrar a un nombre que ya existe en otro método activo
    def test_rename_to_duplicate_fails(self):
        PaymentMethod.objects.create(name='Transferencia', is_active=True)
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Tarjeta', 'new_name': 'Transferencia'}
        response = self.client.patch(reverse('update_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Actualizar un método de pago inexistente devuelve 404
    def test_update_nonexistent_returns_404(self):
        self.client.force_authenticate(user=self.admin)
        data = {'name': 'Inexistente', 'is_active': False}
        response = self.client.patch(reverse('update_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Sin el campo name devuelve 400
    def test_update_without_name_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        data = {'is_active': False}
        response = self.client.patch(reverse('update_payment_method'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PaymentMethodDeleteTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.pm = PaymentMethod.objects.create(name='Tarjeta', is_active=True)

    # El admin elimina (soft delete) un método de pago
    def test_delete_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(
            reverse('delete_payment_method'), {'name': 'Tarjeta'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(PaymentMethod.all_objects.filter(name='Tarjeta').exists())
        self.assertFalse(PaymentMethod.objects.filter(name='Tarjeta').exists())

    # Eliminar un método de pago inexistente devuelve 404
    def test_delete_nonexistent_returns_404(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(
            reverse('delete_payment_method'), {'name': 'Inexistente'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Un miembro no puede eliminar métodos de pago
    def test_delete_as_member_forbidden(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.delete(
            reverse('delete_payment_method'), {'name': 'Tarjeta'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # Un método soft-deleted no aparece en el listado
    def test_deleted_not_in_list(self):
        self.pm.delete()
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('all_payment_methods'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [pm['name'] for pm in response.data]
        self.assertNotIn('Tarjeta', names)
