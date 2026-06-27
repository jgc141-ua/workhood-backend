from decimal import Decimal

from django.template.loader import render_to_string
from weasyprint import HTML


def render_invoice_pdf(invoice):
    issuer_data = {
        'name': invoice.issuer_name,
        'nif': invoice.issuer_nif,
        'address': invoice.issuer_address,
    }

    receiver_data = {
        'name': invoice.user_name,
        'nif': invoice.user_nif,
        'address': invoice.user_address,
        'email': invoice.user.email,
    }

    items = [
        {
            'description': item.description,
            'quantity': item.quantity,
            'unit_price': Decimal(item.unit_price),
            'subtotal': Decimal(item.subtotal),
        }
        for item in invoice.items.all()
    ]

    context = {
        'invoice': invoice,
        'issuer': issuer_data,
        'receiver': receiver_data,
        'items': items,
        'iva_rate_percent': (Decimal(invoice.iva_rate) * 100),
        'tax_base': Decimal(invoice.tax_base),
        'iva_amount': Decimal(invoice.iva_amount),
        'total': Decimal(invoice.total),
    }

    html_string = render_to_string('invoices_payments/pdf.html', context)
    pdf = HTML(string=html_string).write_pdf()
    return pdf