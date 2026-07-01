from rest_framework import serializers

from .timezone import to_utc


class LocalDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        dt = super().to_internal_value(value)
        return to_utc(dt)
