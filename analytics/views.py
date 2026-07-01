from datetime import datetime, time, timedelta

from django.db.models import OuterRef, Q, Subquery, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accesses.models import Access
from invoices_payments.models import Invoice, Payment
from reservations.models import Reservation
from users.models import CustomUser, Resource
from users.permissions import IsOperatorAdmin

from .export import render_revenue_csv


class OccupancyViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsOperatorAdmin]

    # Usuarios con check-in activo (último acceso es ENTRADA sin SALIDA posterior)
    @action(detail=False, methods=['get'], url_path='current')
    def current(self, request):
        last_access_subquery = Access.objects.filter(
            user=OuterRef('user')
        ).order_by('-event').values('id')[:1]

        # Usuarios cuyo último access es ENTRADA
        last_entries = Access.objects.filter(
            id__in=Subquery(last_access_subquery),
            type=Access.ENTRADA,
            result=Access.PERMITIDO,
        )

        # Excluir usuarios que tienen una SALIDA posterior a esa ENTRADA
        active_user_ids = []
        for entry in last_entries:
            has_later_exit = Access.objects.filter(
                user=entry.user,
                type=Access.SALIDA,
                result=Access.PERMITIDO,
                event__gt=entry.event,
            ).exists()
            if not has_later_exit:
                active_user_ids.append(entry.user_id)

        active_accesses = Access.objects.filter(
            user_id__in=active_user_ids,
            id__in=Subquery(last_access_subquery),
        ).select_related('user', 'membership__membership_type').order_by('-event', '-id')

        data = []
        for access in active_accesses:
            data.append({
                'user_id': access.user_id,
                'user_name': access.user_name,
                'user_email': access.user.email,
                'entry_time': access.event,
                'membership_type': access.membership.membership_type.name if access.membership else None,
            })

        return Response({
            'count': len(data),
            'active_checkins': data,
        })

    # Reservas activas en este momento (CONFIRMED con start_time <= now <= end_time)
    @action(detail=False, methods=['get'], url_path='active-reservations')
    def active_reservations(self, request):
        now = timezone.now()

        reservations = Reservation.objects.filter(
            state='Confirmed',
            start_time__lte=now,
            end_time__gte=now,
        ).select_related('user', 'resource').order_by('start_time')

        data = []
        for r in reservations:
            data.append({
                'id': r.id,
                'user_name': f'{r.user.first_name} {r.user.last_name}'.strip(),
                'user_email': r.user.email,
                'resource_id': r.resource_id,
                'resource_name': r.resource.name,
                'start_time': r.start_time,
                'end_time': r.end_time,
                'total_price': float(r.total_price),
            })

        return Response({
            'count': len(data),
            'active_reservations': data,
        })

    # Evolución diaria: para cada hora, cuántos usuarios estuvieron dentro
    @action(detail=False, methods=['get'], url_path='daily-evolution')
    def daily_evolution(self, request):
        date_str = request.query_params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'detail': "Formato de fecha inválido. Use YYYY-MM-DD."},
                    status=400,
                )
        else:
            target_date = timezone.now().date()

        # Genera el rango horario del día (8:00 - 22:00 por defecto, 1h por bucket)
        start_hour = 8
        end_hour = 22
        evolution = []

        for hour in range(start_hour, end_hour + 1):
            bucket_start = datetime.combine(target_date, time(hour=hour))
            bucket_end = bucket_start + timedelta(hours=1)

            # Usuarios con check-in activo en este bucket:
            # - tienen una ENTRADA (PERMITIDO) con event <= bucket_end
            # - y NO tienen una SALIDA (PERMITIDO) con event > ENTRADA y event <= bucket_end
            count = 0
            entries = Access.objects.filter(
                type=Access.ENTRADA,
                result=Access.PERMITIDO,
                event__lte=bucket_end,
                event__date=target_date,
            ).values('id', 'user_id', 'event')

            for entry in entries:
                has_later_exit = Access.objects.filter(
                    user_id=entry['user_id'],
                    type=Access.SALIDA,
                    result=Access.PERMITIDO,
                    event__gt=entry['event'],
                    event__lte=bucket_end,
                ).exists()
                if not has_later_exit:
                    count += 1

            evolution.append({
                'hour': hour,
                'count': count,
            })

        return Response({
            'date': target_date.isoformat(),
            'evolution': evolution,
        })

    # Resumen de miembros (excluye operadores)
    @action(detail=False, methods=['get'], url_path='users-summary')
    def users_summary(self, request):
        members = CustomUser.objects.exclude(role=CustomUser.ADMIN)
        return Response({
            'members_total': members.count(),
            'members_miembro': members.filter(role=CustomUser.MIEMBRO).count(),
            'members_itinerante': members.filter(role=CustomUser.MIEMBRO_ITINERANTE).count(),
        })

    # Resumen de recursos: total vs activos (con reserva CONFIRMED en curso)
    @action(detail=False, methods=['get'], url_path='resources-summary')
    def resources_summary(self, request):
        total = Resource.objects.filter(is_active=True).count()
        now = timezone.now()
        active_ids = Reservation.objects.filter(
            state='Confirmed',
            start_time__lte=now,
            end_time__gte=now,
        ).values_list('resource_id', flat=True).distinct()
        active = Resource.objects.filter(is_active=True, id__in=active_ids).count()
        return Response({
            'resources_total': total,
            'resources_active': active,
        })


# region Reports
# Devuelve (inicio, fin) en datetime según el período.
def _get_period_range(period, ref_date):
    if period == 'day':
        start = datetime.combine(ref_date, time.min)
        end = datetime.combine(ref_date, time.max)
    elif period == 'week':
        # lunes a domingo
        start_date = ref_date - timedelta(days=ref_date.weekday())
        end_date = start_date + timedelta(days=6)
        start = datetime.combine(start_date, time.min)
        end = datetime.combine(end_date, time.max)
    elif period == 'year':
        start = datetime(ref_date.year, 1, 1)
        end = datetime(ref_date.year, 12, 31, 23, 59, 59, 999999)
    else:  # month
        first = ref_date.replace(day=1)
        if first.month == 12:
            next_month = first.replace(year=first.year + 1, month=1)
        else:
            next_month = first.replace(month=first.month + 1)
        start = datetime.combine(first, time.min)
        end = datetime.combine(next_month - timedelta(days=1), time.max)
    return start, end


class ReportsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsOperatorAdmin]

    def _compute_revenue(self, period, date_str):
        if period not in ('day', 'week', 'month', 'year'):
            return {'detail': "period debe ser: day, week, month, year."}, None

        if date_str:
            try:
                ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return {'detail': "Formato de fecha inválido. Use YYYY-MM-DD."}, None
        else:
            ref_date = timezone.now().date()

        start, end = _get_period_range(period, ref_date)

        invoiced_qs = Invoice.objects.filter(
            issue_date__gte=start,
            issue_date__lte=end,
        ).exclude(state=Invoice.ANULADA)

        facturado_total = invoiced_qs.aggregate(t=Sum('total'))['t'] or 0
        cobrado_total = Payment.objects.filter(
            payment_date__gte=start,
            payment_date__lte=end,
        ).aggregate(t=Sum('amount'))['t'] or 0

        # Desglose por plan de membresía
        membership_groups = (
            invoiced_qs.filter(membership__isnull=False)
            .values('membership__membership_type__name')
            .annotate(facturado=Sum('total'))
            .order_by('membership__membership_type__name')
        )
        by_membership = []
        for row in membership_groups:
            name = row['membership__membership_type__name'] or 'Sin nombre'
            facturado = row['facturado'] or 0
            cobrado = Payment.objects.filter(
                payment_date__gte=start,
                payment_date__lte=end,
                invoice__membership__membership_type__name=name,
            ).aggregate(t=Sum('amount'))['t'] or 0
            by_membership.append({
                'name': name,
                'facturado': float(facturado),
                'cobrado': float(cobrado),
            })

        # Desglose por tipo de servicio
        by_service = []
        if invoiced_qs.filter(membership__isnull=True).exists():
            facturado_res = invoiced_qs.filter(membership__isnull=True).aggregate(t=Sum('total'))['t'] or 0
            cobrado_res = Payment.objects.filter(
                payment_date__gte=start,
                payment_date__lte=end,
                invoice__membership__isnull=True,
            ).aggregate(t=Sum('amount'))['t'] or 0
            by_service.append({
                'name': 'Reservas',
                'facturado': float(facturado_res),
                'cobrado': float(cobrado_res),
            })

        # Tendencia 12 meses
        trend = []
        # Empezamos en el mes actual y vamos hacia atrás 12 meses
        year = ref_date.year
        month = ref_date.month
        for i in range(12):
            m = month - i
            y = year
            while m <= 0:
                m += 12
                y -= 1
            from datetime import date as _date
            month_ref = _date(y, m, 1)
            m_start, m_end = _get_period_range('month', month_ref)
            f = Invoice.objects.filter(
                issue_date__gte=m_start,
                issue_date__lte=m_end,
            ).exclude(state=Invoice.ANULADA).aggregate(t=Sum('total'))['t'] or 0
            c = Payment.objects.filter(
                payment_date__gte=m_start,
                payment_date__lte=m_end,
            ).aggregate(t=Sum('amount'))['t'] or 0
            trend.append({
                'month': month_ref.strftime('%Y-%m'),
                'facturado': float(f),
                'cobrado': float(c),
            })
        trend.reverse()

        return None, {
            'period': period,
            'date': ref_date.isoformat(),
            'facturado': float(facturado_total),
            'cobrado': float(cobrado_total),
            'by_membership': by_membership,
            'by_service': by_service,
            'trend': trend,
        }

    @action(detail=False, methods=['get'], url_path='revenue')
    def revenue(self, request):
        period = request.query_params.get('period', 'month')
        date_str = request.query_params.get('date')
        error, data = self._compute_revenue(period, date_str)
        if error:
            return Response(error, status=400)
        return Response(data)

    @action(detail=False, methods=['get'], url_path='revenue-export')
    def revenue_export(self, request):
        period = request.query_params.get('period', 'month')
        date_str = request.query_params.get('date')
        error, data = self._compute_revenue(period, date_str)
        if error:
            return Response(error, status=400)
        return render_revenue_csv(data)
