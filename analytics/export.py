import csv
from io import StringIO

from django.http import HttpResponse


def render_revenue_csv(revenue_data):
    buf = StringIO()
    # BOM para que Excel detecte UTF-8
    buf.write('\ufeff')

    writer = csv.writer(buf, delimiter=';')
    writer.writerow([
        f"Período: {revenue_data['period']}",
        f"Fecha: {revenue_data['date']}",
    ])
    writer.writerow([])
    writer.writerow(['Totales', 'Facturado (€)', 'Cobrado (€)'])
    writer.writerow([
        'TOTAL',
        f"{revenue_data['facturado']:.2f}".replace('.', ','),
        f"{revenue_data['cobrado']:.2f}".replace('.', ','),
    ])
    writer.writerow([])
    writer.writerow(['Desglose por plan de membresía', 'Facturado (€)', 'Cobrado (€)'])
    for row in revenue_data['by_membership']:
        writer.writerow([
            row['name'],
            f"{row['facturado']:.2f}".replace('.', ','),
            f"{row['cobrado']:.2f}".replace('.', ','),
        ])
    writer.writerow([])
    writer.writerow(['Desglose por tipo de servicio', 'Facturado (€)', 'Cobrado (€)'])
    for row in revenue_data['by_service']:
        writer.writerow([
            row['name'],
            f"{row['facturado']:.2f}".replace('.', ','),
            f"{row['cobrado']:.2f}".replace('.', ','),
        ])
    writer.writerow([])
    writer.writerow(['Tendencia 12 meses', 'Facturado (€)', 'Cobrado (€)'])
    for row in revenue_data['trend']:
        writer.writerow([
            row['month'],
            f"{row['facturado']:.2f}".replace('.', ','),
            f"{row['cobrado']:.2f}".replace('.', ','),
        ])

    response = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = (
        f"attachment; filename=ingresos_{revenue_data['date']}_{revenue_data['period']}.csv"
    )
    return response
