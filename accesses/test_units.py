from django.test import TestCase
from django.utils import timezone

from accesses.models import Access
from users.models import Address, CustomUser, Legal


def _make_address():
    return Address.objects.create(
        street='Calle Mayor 1',
        city='Madrid',
        state='Madrid',
        postal_code='28001',
        country='Espana',
    )


def _make_user(email='user@test.com'):
    addr = _make_address()
    user = CustomUser(
        email=email,
        first_name='Test',
        last_name='User',
        nif_cif='12345678Z',
        phone='+34 600000000',
        role=CustomUser.MIEMBRO,
        address=addr,
        billing_address=addr,
    )
    user.save()
    Legal.objects.create(user=user, terms=True, privacy=True, marketing=False)
    return user


class AccessModelTests(TestCase):
    # Desnormalización de campos para tener una snapshot de ellos
    def test_denormalized_fields_survive_user_edits(self):
        user = _make_user(email='original@test.com')
        access = Access.objects.create(
            user=user,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name=f'{user.first_name} {user.last_name}',
            user_email=user.email,
            user_nif_cif=user.nif_cif,
        )
        # El usuario se modifica despues
        user.first_name = 'NewName'
        user.email = 'newemail@test.com'
        user.save()
        # El registro de acceso mantiene los valores originales
        access.refresh_from_db()
        self.assertEqual(access.user_email, 'original@test.com')
        self.assertEqual(access.user_name, 'Test User')
        self.assertEqual(access.user_nif_cif, '12345678Z')

    # El campo event se asigna automaticamente al crear el registro
    def test_event_is_set_automatically(self):
        user = _make_user()
        access = Access.objects.create(
            user=user,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='T U',
            user_email=user.email,
        )
        self.assertIsNotNone(access.event)
        # El evento se acaba de crear
        self.assertLess((timezone.now() - access.event).total_seconds(), 5)

    # Devuelve el acceso más reciente
    def test_ordering_by_most_recent_event(self):
        from datetime import timedelta
        user = _make_user()
        a1 = Access.objects.create(
            user=user,
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
            user_name='T U',
            user_email=user.email,
        )
        # Forzar que a1 tenga un evento anterior seguro
        a1.event = timezone.now() - timedelta(seconds=1)
        a1.save()
        a2 = Access.objects.create(
            user=user,
            type=Access.SALIDA,
            result=Access.PERMITIDO,
            user_name='T U',
            user_email=user.email,
        )
        latest = Access.objects.filter(user=user).order_by('-event').first()
        self.assertEqual(latest.pk, a2.pk)
