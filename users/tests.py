from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import (
    Address,
    Benefit,
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


def _signup_data(email='new@test.com'):
    return {
        'email': email,
        'password': 'Test1234!',
        'password_confirm': 'Test1234!',
        'first_name': 'New',
        'last_name': 'User',
        'phone': '+34 600000000',
        'nif_cif': '12345678Z',
        'address': {
            'street': 'Calle Mayor 1',
            'city': 'Madrid',
            'state': 'Madrid',
            'postal_code': '28001',
            'country': 'España',
        },
        'billing_same_as_address': True,
        'billing_address': {},
        'user_legal': {
            'terms': True,
            'privacy': True,
            'marketing': False,
        },
    }


class SignupTests(APITestCase):
    # El primer usuario registrado se convierte automáticamente en ADMIN
    def test_signup_first_user_becomes_admin(self):
        self.assertEqual(CustomUser.all_objects.count(), 0)
        response = self.client.post(
            reverse('user_signup'), _signup_data('first@test.com'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], 'ADMIN')

    # Los usuarios posteriores al primero se registran como MIEMBRO_ITINERANTE
    def test_signup_subsequent_user_is_miembro_itinerante(self):
        _make_user(email='existing@test.com', role=CustomUser.ADMIN)
        response = self.client.post(
            reverse('user_signup'), _signup_data('new@test.com'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], 'MIEMBRO_ITINERANTE')


class AuthTests(APITestCase):
    # Login con credenciales validas devuelve access y refresh tokens
    def test_login_returns_tokens(self):
        _make_user(email='login@test.com', password='Test1234!')
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'email': 'login@test.com', 'password': 'Test1234!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    # Login con contrasena incorrecta devuelve 401
    def test_login_invalid_credentials(self):
        _make_user(email='login@test.com', password='Test1234!')
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'email': 'login@test.com', 'password': 'wrongpass'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # El endpoint de refresh genera un nuevo access token a partir del refresh
    def test_refresh_token(self):
        _make_user(email='refresh@test.com', password='Test1234!')
        login = self.client.post(
            reverse('token_obtain_pair'),
            {'email': 'refresh@test.com', 'password': 'Test1234!'},
            format='json',
        )
        refresh = login.data['refresh']
        response = self.client.post(
            reverse('token_refresh'), {'refresh': refresh}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)


class ProfileTests(APITestCase):
    def setUp(self):
        self.user = _make_user(email='me@test.com')
        self.client.force_authenticate(user=self.user)

    # El endpoint /me devuelve los datos del usuario autenticado
    def test_me_returns_user_data(self):
        response = self.client.get(reverse('user_me'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'me@test.com')

    # El usuario puede actualizar su propio perfil con PATCH
    def test_update_profile(self):
        data = {'first_name': 'Updated', 'last_name': 'Name'}
        response = self.client.patch(reverse('user_update'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')


class MembersTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.member = _make_user(email='member@test.com', role=CustomUser.MIEMBRO)
        self.client.force_authenticate(user=self.admin)

    # El admin lista todos los miembros activos excluyendose a si mismo
    def test_list_members_as_admin(self):
        response = self.client.get(reverse('members_list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        emails = [m['email'] for m in results]
        self.assertIn('member@test.com', emails)
        self.assertNotIn('admin@test.com', emails)

    # El admin obtiene el detalle de un miembro por su email
    def test_get_member_by_email(self):
        response = self.client.get(
            reverse('admin_member_detail', kwargs={'email': 'member@test.com'})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'member@test.com')

    # El admin puede actualizar los datos de un miembro
    def test_update_member(self):
        data = {'first_name': 'Updated', 'last_name': 'Name'}
        response = self.client.patch(
            reverse('admin_member_detail', kwargs={'email': 'member@test.com'}),
            data,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # Eliminar un miembro hace soft delete: la fila sigue en BD pero no aparece por defecto
    def test_delete_member_is_soft_delete(self):
        response = self.client.delete(
            reverse('members_delete'), {'email': 'member@test.com'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(CustomUser.all_objects.filter(email='member@test.com').exists())
        self.assertFalse(CustomUser.objects.filter(email='member@test.com').exists())

    # Un miembro soft-deleted devuelve 404 al intentar obtenerlo
    def test_deleted_member_returns_404(self):
        self.client.delete(
            reverse('members_delete'), {'email': 'member@test.com'}, format='json'
        )
        response = self.client.get(
            reverse('admin_member_detail', kwargs={'email': 'member@test.com'})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MembershipTypeTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=self.admin)

    # Lista todos los tipos de membresia (activos e inactivos) para admin
    def test_list_all_membership_types(self):
        Membership_Type.objects.create(name='Flex', monthly_price='50.00', is_active=True)
        Membership_Type.objects.create(name='Fixe', monthly_price='100.00', is_fixed=True, is_active=True)
        response = self.client.get(reverse('all_membership_types'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        names = [t['name'] for t in results]
        self.assertIn('Flex', names)
        self.assertIn('Fixe', names)

    # Lista solo los tipos de membresia activos
    def test_list_active_membership_types(self):
        Membership_Type.objects.create(name='Active', monthly_price='50.00', is_active=True)
        Membership_Type.objects.create(name='Inactive', monthly_price='50.00', is_active=False)
        response = self.client.get(reverse('active_membership_types'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        names = [t['name'] for t in results]
        self.assertIn('Active', names)
        self.assertNotIn('Inactive', names)

    # El admin crea un nuevo tipo de membresia
    def test_create_membership_type(self):
        data = {
            'name': 'NewType',
            'description': 'Test',
            'monthly_price': '50.00',
            'is_fixed': False,
            'is_active': True,
        }
        response = self.client.post(reverse('create_membership_type'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Membership_Type.objects.filter(name='NewType').exists())

    # No se puede crear un tipo de membresia con un nombre ya existente activo
    def test_duplicate_name_fails(self):
        Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        data = {'name': 'Flex', 'description': 'Dup', 'monthly_price': '50.00'}
        response = self.client.post(reverse('create_membership_type'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Eliminar un tipo de membresia hace soft delete
    def test_delete_membership_type_is_soft_delete(self):
        Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        response = self.client.delete(
            reverse('delete_membership_type'), {'name': 'Flex'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Membership_Type.all_objects.filter(name='Flex').exists())
        self.assertFalse(Membership_Type.objects.filter(name='Flex').exists())


class BenefitTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=self.admin)

    # El admin lista todos los beneficios
    def test_list_benefits(self):
        Benefit.objects.create(name='WiFi', description='WiFi alta velocidad')
        response = self.client.get(reverse('all_benefits'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # El admin crea un nuevo beneficio
    def test_create_benefit(self):
        data = {'name': 'Coffee', 'description': 'Free coffee', 'quantity': 10}
        response = self.client.post(reverse('create_benefit'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Benefit.objects.filter(name='Coffee').exists())

    # Eliminar un beneficio hace soft delete
    def test_delete_benefit_is_soft_delete(self):
        Benefit.objects.create(name='WiFi', description='WiFi')
        response = self.client.delete(
            reverse('delete_benefit'), {'name': 'WiFi'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Benefit.all_objects.filter(name='WiFi').exists())
        self.assertFalse(Benefit.objects.filter(name='WiFi').exists())


class ResourceTypeTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=self.admin)

    # El admin lista todos los tipos de recurso
    def test_list_resource_types(self):
        Resource_Type.objects.create(name='Sala', description='Sala de reuniones')
        response = self.client.get(reverse('all_resource_types'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # El admin crea un nuevo tipo de recurso
    def test_create_resource_type(self):
        data = {'name': 'Escritorio', 'description': 'Escritorio individual'}
        response = self.client.post(reverse('create_resource_type'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Resource_Type.objects.filter(name='Escritorio').exists())

    # Eliminar un tipo de recurso hace soft delete
    def test_delete_resource_type_is_soft_delete(self):
        Resource_Type.objects.create(name='Sala', description='Sala')
        response = self.client.delete(
            reverse('delete_resource_type'), {'name': 'Sala'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Resource_Type.all_objects.filter(name='Sala').exists())
        self.assertFalse(Resource_Type.objects.filter(name='Sala').exists())


class ResourceTests(APITestCase):
    def setUp(self):
        self.admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.rt = Resource_Type.objects.create(name='Sala', description='Sala')
        self.client.force_authenticate(user=self.admin)

    # El admin lista todos los recursos
    def test_list_resources(self):
        Resource.objects.create(
            name='Sala 1', capacity=10, price='15.00', resource_type=self.rt
        )
        response = self.client.get(reverse('all_resources'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # El admin crea un nuevo recurso
    def test_create_resource(self):
        data = {
            'name': 'Sala 1',
            'description': 'Sala',
            'capacity': 10,
            'price': '15.00',
            'resource_type': self.rt.id,
        }
        response = self.client.post(reverse('create_resource'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Resource.objects.filter(name='Sala 1').exists())

    # Eliminar un recurso hace soft delete
    def test_delete_resource_is_soft_delete(self):
        r = Resource.objects.create(
            name='Sala 1', capacity=10, price='15.00', resource_type=self.rt
        )
        response = self.client.delete(
            reverse('delete_resource'), {'id': r.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Resource.all_objects.filter(name='Sala 1').exists())
        self.assertFalse(Resource.objects.filter(name='Sala 1').exists())


class MembershipTests(APITestCase):
    def setUp(self):
        self.user = _make_user(
            email='member@test.com', role=CustomUser.MIEMBRO_ITINERANTE
        )
        self.mt = Membership_Type.objects.create(
            name='Flex', monthly_price='50.00', is_active=True
        )
        self.client.force_authenticate(user=self.user)

    # Si el usuario no tiene membresia activa devuelve 404
    def test_my_membership_none(self):
        response = self.client.get(reverse('my_membership'))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Devuelve la membresia activa del usuario autenticado
    def test_my_membership_active(self):
        Membership.objects.create(
            user=self.user,
            membership_type=self.mt,
            price='50.00',
            end_date=timezone.now() + timedelta(days=10),
            is_active=True,
        )
        response = self.client.get(reverse('my_membership'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['membership_type_name'], 'Flex')

    # Suscribirse crea una nueva membresia y actualiza el rol a MIEMBRO
    def test_subscribe_creates_membership(self):
        data = {'membership_type': self.mt.id, 'auto_renew': True}
        response = self.client.post(reverse('subscribe'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Membership.objects.filter(user=self.user, membership_type=self.mt).exists()
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, CustomUser.MIEMBRO)

    # Suscribirse a una membresia de tipo fijo sin recurso falla con 400
    def test_subscribe_with_fixed_requires_resource(self):
        fixed_mt = Membership_Type.objects.create(
            name='Fixe', monthly_price='100.00', is_fixed=True, is_active=True
        )
        data = {'membership_type': fixed_mt.id}
        response = self.client.post(reverse('subscribe'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # El admin puede cancelar la membresia activa de un miembro
    def test_cancel_membership_by_admin(self):
        Membership.objects.create(
            user=self.user,
            membership_type=self.mt,
            price='50.00',
            end_date=timezone.now() + timedelta(days=10),
            is_active=True,
        )
        admin = _make_user(email='admin@test.com', role=CustomUser.ADMIN)
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            reverse('cancel_membership'), {'email': 'member@test.com'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, CustomUser.MIEMBRO_ITINERANTE)
