from datetime import date, datetime

from django.test import TestCase

from analytics.views import _get_period_range


class GetPeriodRangeTests(TestCase):
    # 'day' cubre el dia completo
    def test_day_spans_full_day(self):
        ref = date(2026, 6, 15)
        start, end = _get_period_range('day', ref)
        self.assertEqual(start, datetime(2026, 6, 15, 0, 0, 0))
        self.assertEqual(end, datetime(2026, 6, 15, 23, 59, 59, 999999))

    # 'week' empieza en lunes
    def test_week_starts_on_monday(self):
        # 2026-06-17 es miercoles
        ref = date(2026, 6, 17)
        start, end = _get_period_range('week', ref)
        self.assertEqual(start.date(), date(2026, 6, 15))
        self.assertEqual(end.date(), date(2026, 6, 21))

    def test_week_for_monday_is_same_week(self):
        # 2026-06-15 es lunes
        ref = date(2026, 6, 15)
        start, end = _get_period_range('week', ref)
        self.assertEqual(start.date(), date(2026, 6, 15))
        self.assertEqual(end.date(), date(2026, 6, 21))

    def test_week_for_sunday_ends_same_day(self):
        # 2026-06-21 es domingo
        ref = date(2026, 6, 21)
        start, end = _get_period_range('week', ref)
        self.assertEqual(start.date(), date(2026, 6, 15))
        self.assertEqual(end.date(), date(2026, 6, 21))

    # 'month' cubre del dia 1 al ultimo dia del mes
    def test_month_spans_full_month(self):
        ref = date(2026, 6, 15)
        start, end = _get_period_range('month', ref)
        self.assertEqual(start.date(), date(2026, 6, 1))
        self.assertEqual(end.date(), date(2026, 6, 30))

    # Caso limite: diciembre no se desborda a enero del año siguiente
    def test_december_ends_on_31(self):
        ref = date(2026, 12, 15)
        start, end = _get_period_range('month', ref)
        self.assertEqual(start.date(), date(2026, 12, 1))
        self.assertEqual(end.date(), date(2026, 12, 31))

    # 'year' cubre del 1 de enero al 31 de diciembre
    def test_year_spans_full_year(self):
        ref = date(2026, 6, 15)
        start, end = _get_period_range('year', ref)
        self.assertEqual(start, datetime(2026, 1, 1, 0, 0, 0))
        self.assertEqual(end, datetime(2026, 12, 31, 23, 59, 59, 999999))

    # Cualquier otro valor cae en la rama por defecto y se trata como 'month'
    def test_unknown_period_falls_back_to_month(self):
        ref = date(2026, 6, 15)
        start, end = _get_period_range('foo', ref)
        self.assertEqual(start.date(), date(2026, 6, 1))
        self.assertEqual(end.date(), date(2026, 6, 30))
