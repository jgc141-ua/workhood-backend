from datetime import timedelta, timezone as dt_timezone

from dateutil.relativedelta import relativedelta
from django.db import models, transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Reservation, SpaceSchedule


# region SpaceSchedule
class SpaceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpaceSchedule
        fields = [
            'id',
            'start_date',
            'end_date',
            'opening_time',
            'closing_time',
            'is_open',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# region Reservation
class ReservationSerializer(serializers.ModelSerializer):
    resource_name = serializers.CharField(source='resource.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id',
            'start_time',
            'end_time',
            'state',
            'reservation_type',
            'recurrence_end_date',
            'total_price',
            'created_at',
            'updated_at',
            'user',
            'user_email',
            'resource',
            'resource_name',
            'membership',
        ]
        read_only_fields = [
            'id',
            'state',
            'created_at',
            'updated_at',
            'user',
            'user_email',
            'membership',
            'total_price',
        ]


# region ReservationCreate
class ReservationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'resource',
            'start_time',
            'end_time',
            'reservation_type',
            'recurrence_end_date',
        ]

    def validate_resource(self, value):
        if not value.is_active or not value.availability:
            raise serializers.ValidationError("El recurso seleccionado no está disponible.")
        return value

    def validate(self, data):
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        reservation_type = data.get('reservation_type')
        recurrence_end_date = data.get('recurrence_end_date')

        if start_time < timezone.now():
            raise serializers.ValidationError("No se puede reservar en el pasado.")

        if start_time >= end_time:
            raise serializers.ValidationError("La fecha de inicio debe ser anterior a la fecha de fin.")

        if reservation_type in (Reservation.WEEKLY, Reservation.MONTHLY):
            if not recurrence_end_date:
                raise serializers.ValidationError(
                    {"recurrence_end_date": "La fecha de fin de recurrencia es obligatoria."}
                )
            if recurrence_end_date <= start_time:
                raise serializers.ValidationError(
                    {"recurrence_end_date": "La fecha de fin debe ser posterior a la fecha de inicio."}
                )

        if reservation_type == Reservation.DAILY:
            schedule = SpaceSchedule.objects.filter(
                models.Q(start_date__lte=start_time.date()),
                models.Q(end_date__gte=start_time.date()) | models.Q(end_date__isnull=True),
            ).first()

            if not schedule or not schedule.is_open:
                raise serializers.ValidationError(
                    f"El espacio está cerrado el {start_time.date()}."
                )

            data['start_time'] = start_time.replace(
                hour=schedule.opening_time.hour,
                minute=schedule.opening_time.minute,
                second=0,
                microsecond=0,
            )
            data['end_time'] = end_time.replace(
                hour=schedule.closing_time.hour,
                minute=schedule.closing_time.minute,
                second=0,
                microsecond=0,
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        resource = validated_data['resource']
        start_time = validated_data['start_time']
        end_time = validated_data['end_time']
        reservation_type = validated_data['reservation_type']
        recurrence_end_date = validated_data.get('recurrence_end_date')

        # Genera las ocurrencias de la reserva
        occurrences = self._generate_occurrences(
            start_time, end_time, reservation_type, recurrence_end_date
        )

        # Valida horario y solapamiento para cada ocurrencia
        for occ_start, occ_end in occurrences:
            self._validate_space_schedule(occ_start, occ_end)
            self._validate_no_overlap(resource, occ_start, occ_end)

        # Crea todas las reservas con su precio calculado
        created_reservations = []
        for occ_start, occ_end in occurrences:
            total_price = self._calculate_total_price(resource, occ_start, occ_end)
            reservation = Reservation.objects.create(
                user=user,
                resource=resource,
                start_time=occ_start,
                end_time=occ_end,
                reservation_type=reservation_type,
                recurrence_end_date=recurrence_end_date,
                total_price=total_price,
                state=Reservation.CONFIRMED,
            )
            created_reservations.append(reservation)

        # Devuelve la primera reserva creada
        return created_reservations[0]

    def _calculate_total_price(self, resource, start_time, end_time):
        hours = (end_time - start_time).total_seconds() / 3600
        return round(float(resource.price) * hours, 2)

    def _generate_occurrences(self, start_time, end_time, reservation_type, recurrence_end_date):
        duration = end_time - start_time
        occurrences = []

        if reservation_type in (Reservation.HOURLY, Reservation.DAILY):
            occurrences.append((start_time, end_time))
            return occurrences

        max_occurrences = 52 if reservation_type == Reservation.WEEKLY else 12
        current_start = start_time
        count = 0

        while current_start <= recurrence_end_date and count < max_occurrences:
            current_end = current_start + duration
            occurrences.append((current_start, current_end))

            if reservation_type == Reservation.WEEKLY:
                current_start += timedelta(weeks=1)
            elif reservation_type == Reservation.MONTHLY:
                current_start += relativedelta(months=1)

            count += 1

        return occurrences

    def _validate_space_schedule(self, start_time, end_time):
        schedule = SpaceSchedule.objects.filter(
            start_date__lte=start_time.date(),
        ).filter(
            models.Q(end_date__gte=start_time.date()) | models.Q(end_date__isnull=True)
        ).first()

        if not schedule or not schedule.is_open:
            raise serializers.ValidationError(f"El espacio está cerrado el {start_time.date()}.")

        start_naive = timezone.make_naive(start_time, dt_timezone.utc)
        end_naive = timezone.make_naive(end_time, dt_timezone.utc)

        if start_naive.time() < schedule.opening_time or end_naive.time() > schedule.closing_time:
            raise serializers.ValidationError(
                f"La reserva debe estar dentro del horario ({schedule.opening_time} - {schedule.closing_time})."
            )

    def _validate_no_overlap(self, resource, start_time, end_time):
        has_overlap = Reservation.objects.filter(
            resource=resource,
            state__in=(Reservation.PENDING, Reservation.CONFIRMED),
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).exists()

        if has_overlap:
            raise serializers.ValidationError("El recurso ya está reservado en esa franja horaria.")
