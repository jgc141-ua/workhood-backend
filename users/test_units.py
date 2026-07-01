from django.test import TestCase

from users.models import (
    Address,
    CustomUser,
    Legal,
    Membership_Type,
)


def _make_address():
    return Address.objects.create(
        street='Calle Mayor 1',
        city='Madrid',
        state='Madrid',
        postal_code='28001',
        country='Espana',
    )


def _make_user(email='user@test.com', role=CustomUser.MIEMBRO):
    addr = _make_address()
    user = CustomUser(
        email=email,
        first_name='Test',
        last_name='User',
        nif_cif='12345678Z',
        phone='+34 600000000',
        role=role,
        address=addr,
        billing_address=addr,
    )
    user.save()
    Legal.objects.create(user=user, terms=True, privacy=True, marketing=False)
    return user


class SoftDeleteModelTests(TestCase):
    # SoftDeleteModel.delete() marca deleted_at pero NO elimina la fila
    def test_instance_delete_is_soft(self):
        mt = Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        pk = mt.pk
        mt.delete()
        mt.refresh_from_db()
        self.assertIsNotNone(mt.deleted_at)
        self.assertTrue(Membership_Type.all_objects.filter(pk=pk).exists())

    # El manager por defecto oculta los soft-deleted
    def test_default_manager_hides_soft_deleted(self):
        active = Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        deleted = Membership_Type.objects.create(name='Fixe', monthly_price='100.00')
        deleted.delete()

        self.assertEqual(Membership_Type.objects.count(), 1)
        self.assertEqual(Membership_Type.all_objects.count(), 2)
        self.assertIn(active, Membership_Type.objects.all())
        self.assertNotIn(deleted, Membership_Type.objects.all())

    # all_objects expone el conjunto completo, incluidos soft-deleted
    def test_all_objects_exposes_everything(self):
        a = Membership_Type.objects.create(name='A', monthly_price='10.00')
        b = Membership_Type.objects.create(name='B', monthly_price='20.00')
        b.delete()
        ids = {m.pk for m in Membership_Type.all_objects.all()}
        self.assertEqual(ids, {a.pk, b.pk})

    # restore() devuelve el registro a la vista del manager por defecto
    def test_restore_undoes_soft_delete(self):
        mt = Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        mt.delete()
        self.assertEqual(Membership_Type.objects.count(), 0)

        mt.restore()
        mt.refresh_from_db()
        self.assertIsNone(mt.deleted_at)
        self.assertEqual(Membership_Type.objects.count(), 1)

    # hard_delete() elimina la fila de la base de datos
    def test_hard_delete_removes_row(self):
        mt = Membership_Type.objects.create(name='Flex', monthly_price='50.00')
        pk = mt.pk
        mt.hard_delete()
        self.assertFalse(Membership_Type.all_objects.filter(pk=pk).exists())

    # QuerySet.delete() hace soft delete en lote
    def test_queryset_delete_is_soft(self):
        a = Membership_Type.objects.create(name='A', monthly_price='10.00')
        b = Membership_Type.objects.create(name='B', monthly_price='20.00')
        Membership_Type.objects.filter(pk__in=[a.pk, b.pk]).delete()

        self.assertEqual(Membership_Type.objects.count(), 0)
        self.assertEqual(Membership_Type.all_objects.count(), 2)

    # Comprobar membresías muertas o vivas (con softdelete)
    def test_alive_and_dead_querysets(self):
        a = Membership_Type.objects.create(name='A', monthly_price='10.00')
        b = Membership_Type.objects.create(name='B', monthly_price='20.00')
        b.delete()

        # Devuelve solo los no soft-deleted
        self.assertIn(a, Membership_Type.objects.alive())
        self.assertNotIn(b, Membership_Type.objects.alive())
        # Ya excluye los soft-deleted
        self.assertIn(a, Membership_Type.objects.all())
        self.assertNotIn(b, Membership_Type.objects.all())
        # all_objects expone el conjunto completo
        self.assertIn(a, Membership_Type.all_objects.all())
        self.assertIn(b, Membership_Type.all_objects.all())


class CustomUserSoftDeleteTests(TestCase):
    # CustomUser usa SoftDeleteUserManager: objects oculta, all_objects no
    def test_user_soft_delete_hides_from_default_manager(self):
        user = _make_user(email='x@test.com')
        user.delete()
        self.assertFalse(CustomUser.objects.filter(email='x@test.com').exists())
        self.assertTrue(CustomUser.all_objects.filter(email='x@test.com').exists())

    # El check de signup mira all_objects para no permitir emails de soft-deleted
    def test_all_objects_used_to_prevent_duplicate_signup(self):
        user = _make_user(email='taken@test.com')
        user.delete()
        # all_objects debe seguir encontrando el email aunque este soft-deleted
        self.assertTrue(CustomUser.all_objects.filter(email='taken@test.com').exists())
        # El check de signup si
        self.assertFalse(CustomUser.objects.filter(email='taken@test.com').exists())

    # restore() en CustomUser devuelve el rol a su estado original
    def test_restore_keeps_user_data_intact(self):
        user = _make_user(email='x@test.com', role=CustomUser.MIEMBRO)
        original_role = user.role
        user.delete()
        user.restore()
        user.refresh_from_db()
        self.assertIsNone(user.deleted_at)
        self.assertEqual(user.role, original_role)
        self.assertTrue(CustomUser.objects.filter(email='x@test.com').exists())
