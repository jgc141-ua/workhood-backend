from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from invoices_payments.models import Invoice, PaymentMethod
from invoices_payments.serializers import (
    _create_invoice,
    _generate_invoice_number,
    _mark_overdue_invoices_bulk,
    _process_renewals_bulk,
    register_payment,
)
from reservations.models import Reservation
from users.models import (
    Address,
    CustomUser,
    Membership,
    Membership_Type,
    Resource,
    Resource_Type,
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
    return user


def _make_membership_type(name='Flex', price='50.00'):
    return Membership_Type.objects.create(
        name=name,
        monthly_price=Decimal(price),
        is_active=True,
    )


def _make_membership(user, mt=None, end_date=None, auto_renew=True):
    if mt is None:
        mt = _make_membership_type()
    return Membership.objects.create(
        user=user,
        membership_type=mt,
        price=mt.monthly_price,
        end_date=end_date or (timezone.now() + timedelta(days=10)),
        is_active=True,
        auto_renew=auto_renew,
    )


def _make_payment_method(name='Tarjeta'):
    return PaymentMethod.objects.create(name=name, is_active=True)


def _make_resource(name='Sala 1', price='10.00'):
    rt = Resource_Type.objects.create(name='Sala', description='Sala')
    return Resource.objects.create(
        name=name,
        capacity=10,
        price=Decimal(price),
        resource_type=rt,
        is_active=True,
    )


class GenerateInvoiceNumberTests(TestCase):
    # La primera factura del año recibe el secuencial 000001
    def test_first_invoice_number_format(self):
        number = _generate_invoice_number()
        year = timezone.now().year
        self.assertEqual(number, f'INV-{year}-000001')

    # Facturas consecutivas incrementan el secuencial dentro del mismo año
    def test_sequential_numbers_in_same_year(self):
        user = _make_user()
        mt = _make_membership_type()
        membership = _make_membership(user, mt)
        i1 = _create_invoice(user=user, concept='A', amount='10.00', membership=membership)
        i2 = _create_invoice(user=user, concept='B', amount='10.00', membership=membership)
        self.assertEqual(i1.invoice_number.split('-')[-1], '000001')
        self.assertEqual(i2.invoice_number.split('-')[-1], '000002')


class CreateInvoiceTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    # IVA (21%) y total se calculan a partir de la base imponible
    def test_iva_and_total_calculated_from_tax_base(self):
        invoice = _create_invoice(user=self.user, concept='Test', amount='100.00')
        self.assertEqual(invoice.tax_base, Decimal('100.00'))
        self.assertEqual(invoice.iva_rate, Decimal('0.21'))
        self.assertEqual(invoice.iva_amount, Decimal('21.00'))
        self.assertEqual(invoice.total, Decimal('121.00'))

    # Las nuevas facturas se crean en estado EMITIDA
    def test_invoice_starts_in_emitida_state(self):
        invoice = _create_invoice(user=self.user, concept='Test', amount='10.00')
        self.assertEqual(invoice.state, Invoice.EMITIDA)

    # Cada factura lleva su InvoiceItem con el mismo importe
    def test_creates_invoice_item_with_same_amount(self):
        invoice = _create_invoice(user=self.user, concept='Test', amount='50.00')
        items = list(invoice.items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].subtotal, Decimal('50.00'))
        self.assertEqual(items[0].unit_price, Decimal('50.00'))
        self.assertEqual(items[0].quantity, Decimal('1'))

    # El calculo del IVA redondea correctamente a 2 decimales
    def test_iva_decimal_quantization(self):
        # 33.33 * 0.21 = 6.9993 -> 7.00
        invoice = _create_invoice(user=self.user, concept='Test', amount='33.33')
        self.assertEqual(invoice.iva_amount, Decimal('7.00'))
        self.assertEqual(invoice.total, Decimal('40.33'))

    # Si no se pasa due_date, se asigna un plazo de 7 dias desde ahora
    def test_default_due_date_is_7_days_from_now(self):
        before = timezone.now()
        invoice = _create_invoice(user=self.user, concept='Test', amount='10.00')
        self.assertGreater(invoice.due_date, before + timedelta(days=6, hours=23))
        self.assertLess(invoice.due_date, before + timedelta(days=7, hours=1))

    # El numero de factura se asigna al crear
    def test_invoice_number_assigned(self):
        invoice = _create_invoice(user=self.user, concept='Test', amount='10.00')
        year = timezone.now().year
        self.assertTrue(invoice.invoice_number.startswith(f'INV-{year}-'))


class RegisterPaymentTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.mt = _make_membership_type()
        self.membership = _make_membership(self.user, self.mt)
        self.invoice = _create_invoice(
            user=self.user,
            concept='Test',
            amount='50.00',
            membership=self.membership,
        )
        self.method = _make_payment_method()

    # Un pago parcial no marca la factura como PAGADA
    def test_partial_payment_does_not_mark_as_pagada(self):
        register_payment(self.invoice, '30.00', self.method)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.state, Invoice.EMITIDA)

    # Cubrir el total marca la factura como PAGADA
    def test_full_payment_marks_as_pagada(self):
        register_payment(self.invoice, self.invoice.total, self.method)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.state, Invoice.PAGADA)

    # Al pagar la factura, las reservas PENDING vinculadas pasan a CONFIRMED
    def test_full_payment_confirms_linked_pending_reservation(self):
        resource = _make_resource()
        reservation = Reservation.objects.create(
            user=self.user,
            resource=resource,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=1),
            reservation_type='HOURLY',
            state='Pending',
            invoice=self.invoice,
            total_price=Decimal('10.00'),
        )
        register_payment(self.invoice, self.invoice.total, self.method)
        reservation.refresh_from_db()
        self.assertEqual(reservation.state, 'Confirmed')

    # El pago registra el importe y el metodo correctos
    def test_payment_records_amount_and_method(self):
        register_payment(self.invoice, '50.00', self.method)
        payment = self.invoice.payments.first()
        self.assertEqual(payment.amount, Decimal('50.00'))
        self.assertEqual(payment.method, self.method)


class MarkOverdueInvoicesTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.mt = _make_membership_type()
        self.membership = _make_membership(self.user, self.mt)
        self.resource = _make_resource()

    # Factura EMITIDA con due_date en el pasado pasa a VENCIDA
    def test_overdue_emitida_marks_as_vencida(self):
        past = timezone.now() - timedelta(days=1)
        invoice = _create_invoice(
            user=self.user,
            concept='T',
            amount='10.00',
            due_date=past,
            membership=self.membership,
        )
        _mark_overdue_invoices_bulk()
        invoice.refresh_from_db()
        self.assertEqual(invoice.state, Invoice.VENCIDA)

    # Factura EMITIDA con due_date en el futuro sigue EMITIDA
    def test_not_yet_due_stays_emitida(self):
        future = timezone.now() + timedelta(days=5)
        invoice = _create_invoice(
            user=self.user,
            concept='T',
            amount='10.00',
            due_date=future,
            membership=self.membership,
        )
        _mark_overdue_invoices_bulk()
        invoice.refresh_from_db()
        self.assertEqual(invoice.state, Invoice.EMITIDA)

    # Las reservas vinculadas a la factura vencida se cancelan
    def test_overdue_cancels_linked_reservation(self):
        past = timezone.now() - timedelta(days=1)
        invoice = _create_invoice(
            user=self.user,
            concept='T',
            amount='10.00',
            due_date=past,
            membership=self.membership,
        )
        reservation = Reservation.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=1),
            reservation_type='HOURLY',
            state='Pending',
            invoice=invoice,
            total_price=Decimal('10.00'),
        )
        _mark_overdue_invoices_bulk()
        reservation.refresh_from_db()
        self.assertEqual(reservation.state, 'Cancelled')

    # La membresia vinculada a la factura vencida se desactiva
    def test_overdue_deactivates_linked_membership(self):
        past = timezone.now() - timedelta(days=1)
        _create_invoice(
            user=self.user,
            concept='T',
            amount='10.00',
            due_date=past,
            membership=self.membership,
        )
        _mark_overdue_invoices_bulk()
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_active)

    # El usuario con membresia vencida pasa a MIEMBRO_ITINERANTE
    def test_overdue_downgrades_user_role(self):
        past = timezone.now() - timedelta(days=1)
        _create_invoice(
            user=self.user,
            concept='T',
            amount='10.00',
            due_date=past,
            membership=self.membership,
        )
        _mark_overdue_invoices_bulk()
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, CustomUser.MIEMBRO_ITINERANTE)


class ProcessRenewalsTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.mt = _make_membership_type(price='50.00')

    # Renueva una membresia con auto_renew=True que ya ha vencido
    def test_renews_expired_auto_renew_membership(self):
        expired = _make_membership(
            self.user,
            self.mt,
            end_date=timezone.now() - timedelta(days=1),
            auto_renew=True,
        )
        _process_renewals_bulk()
        expired.refresh_from_db()
        # La original se desactiva
        self.assertFalse(expired.is_active)
        # Se crea una nueva membresia activa del mismo tipo
        new_membership = (
            Membership.objects
            .filter(user=self.user, is_active=True)
            .exclude(pk=expired.pk)
            .first()
        )
        self.assertIsNotNone(new_membership)
        self.assertEqual(new_membership.membership_type, self.mt)

    # No renueva membresias sin auto_renew aunque esten vencidas
    def test_does_not_renew_non_auto_renew(self):
        expired = _make_membership(
            self.user,
            self.mt,
            end_date=timezone.now() - timedelta(days=1),
            auto_renew=False,
        )
        _process_renewals_bulk()
        # Sigue existiendo solo la original y se mantiene activa
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)
        expired.refresh_from_db()
        self.assertTrue(expired.is_active)

    # La nueva membresia lleva su factura EMITIDA correspondiente
    def test_renewal_creates_invoice(self):
        _make_membership(
            self.user,
            self.mt,
            end_date=timezone.now() - timedelta(days=1),
            auto_renew=True,
        )
        _process_renewals_bulk()
        new_invoice = (
            Invoice.objects
            .filter(user=self.user, membership__isnull=False)
            .order_by('-issue_date')
            .first()
        )
        self.assertIsNotNone(new_invoice)
        self.assertEqual(new_invoice.tax_base, Decimal('50.00'))
        self.assertEqual(new_invoice.state, Invoice.EMITIDA)

    # Las membresias que aun no han vencido no se tocan
    def test_does_not_renew_active_membership(self):
        _make_membership(
            self.user,
            self.mt,
            end_date=timezone.now() + timedelta(days=10),
            auto_renew=True,
        )
        _process_renewals_bulk()
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)
