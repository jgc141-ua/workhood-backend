from datetime import datetime, timezone as dt_timezone

from django.db import models
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.pagination import Pagination
from users.models import Resource
from users.permissions import IsOperatorAdmin

from .models import Reservation, SpaceSchedule
from .serializers import (
    ReservationCreateSerializer,
    ReservationSerializer,
    SpaceScheduleSerializer,
)


# region SpaceSchedule
class SpaceScheduleViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsOperatorAdmin]

    def get_queryset(self):
        return SpaceSchedule.objects.all()

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        queryset = self.get_queryset().order_by('-start_date')
        paginator = Pagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = SpaceScheduleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['post'], url_path='create')
    def create(self, request):
        serializer = SpaceScheduleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['put', 'patch'], url_path='update')
    def update(self, request):
        schedule_id = request.data.get('id')
        if not schedule_id:
            return Response({"detail": "El campo 'id' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            schedule = SpaceSchedule.objects.get(pk=schedule_id)
        except SpaceSchedule.DoesNotExist:
            return Response({"detail": "Horario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SpaceScheduleSerializer(schedule, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['delete'], url_path='delete')
    def delete(self, request):
        schedule_id = request.data.get('id')
        if not schedule_id:
            return Response({"detail": "El campo 'id' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            schedule = SpaceSchedule.objects.get(pk=schedule_id)
        except SpaceSchedule.DoesNotExist:
            return Response({"detail": "Horario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# region Reservations
class ReservationsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='my')
    def my_reservations(self, request):
        queryset = Reservation.objects.filter(user=request.user).order_by('-start_time')

        # Filtros opcionales
        state = request.query_params.get('state')
        resource_type = request.query_params.get('resource_type')
        upcoming = request.query_params.get('upcoming')

        if state:
            queryset = queryset.filter(state=state)
        if resource_type:
            queryset = queryset.filter(resource__resource_type=resource_type)
        if upcoming == 'true':
            queryset = queryset.filter(start_time__gte=timezone.now())
        elif upcoming == 'false':
            queryset = queryset.filter(start_time__lt=timezone.now())

        serializer = ReservationSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='create')
    def create_reservation(self, request):
        serializer = ReservationCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            reservation = serializer.save()
            response_serializer = ReservationSerializer(reservation)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='availability')
    def availability(self, request):
        resource_id = request.query_params.get('resource')
        start_time_str = request.query_params.get('start_time')
        end_time_str = request.query_params.get('end_time')

        if not resource_id or not start_time_str or not end_time_str:
            return Response(
                {"detail": "Los parámetros 'resource', 'start_time' y 'end_time' son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return Response({"detail": "Recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not resource.is_active or not resource.availability:
            return Response({"available": False, "reason": "El recurso no está disponible."})

        start_time = parse_datetime(start_time_str)
        end_time = parse_datetime(end_time_str)

        if not start_time or not end_time:
            return Response({"detail": "Formato de fecha inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if start_time >= end_time:
            return Response(
                {"detail": "La fecha de inicio debe ser anterior a la fecha de fin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        overlapping = Reservation.objects.filter(
            resource=resource,
            state__in=(Reservation.PENDING, Reservation.CONFIRMED),
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).exists()

        if overlapping:
            return Response({"available": False, "reason": "El recurso ya está reservado en esa franja."})

        return Response({"available": True})

    @action(detail=False, methods=['get'], url_path='resource-schedule')
    def resource_schedule(self, request):
        resource_id = request.query_params.get('resource')
        date_str = request.query_params.get('date')

        if not resource_id or not date_str:
            return Response(
                {"detail": "Los parámetros 'resource' y 'date' son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return Response({"detail": "Recurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        target_date = parse_date(date_str)
        if not target_date:
            return Response({"detail": "Formato de fecha inválido."}, status=status.HTTP_400_BAD_REQUEST)

        schedule = SpaceSchedule.objects.filter(
            start_date__lte=target_date,
        ).filter(
            models.Q(end_date__gte=target_date) | models.Q(end_date__isnull=True)
        ).annotate(
            is_specific=models.Case(
                models.When(end_date__isnull=False, then=0),
                default=1,
                output_field=models.IntegerField(),
            )
        ).order_by('is_specific', '-start_date').first()

        if not schedule or not schedule.is_open:
            return Response({
                "resource": resource.id,
                "date": date_str,
                "is_open": False,
                "blocks": [],
            })

        opening = datetime.combine(target_date, schedule.opening_time)
        closing = datetime.combine(target_date, schedule.closing_time)

        reservations = Reservation.objects.filter(
            resource=resource,
            state__in=(Reservation.PENDING, Reservation.CONFIRMED),
            start_time__date=target_date,
        ).order_by('start_time')

        blocks = []
        current = opening

        for reservation in reservations:
            res_start = timezone.make_naive(reservation.start_time, dt_timezone.utc)
            res_end = timezone.make_naive(reservation.end_time, dt_timezone.utc)

            if res_start > current:
                blocks.append({
                    "start_time": current.strftime("%H:%M"),
                    "end_time": res_start.strftime("%H:%M"),
                    "status": "free",
                })
            blocks.append({
                "start_time": res_start.strftime("%H:%M"),
                "end_time": res_end.strftime("%H:%M"),
                "status": "occupied",
            })
            current = max(current, res_end)

        if current < closing:
            blocks.append({
                "start_time": current.strftime("%H:%M"),
                "end_time": closing.strftime("%H:%M"),
                "status": "free",
            })

        return Response({
            "resource": resource.id,
            "date": date_str,
            "is_open": True,
            "opening_time": schedule.opening_time.strftime("%H:%M"),
            "closing_time": schedule.closing_time.strftime("%H:%M"),
            "blocks": blocks,
        })
