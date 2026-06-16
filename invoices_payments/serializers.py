from rest_framework import serializers

from .models import PaymentMethod


# region PaymentMethod
class PaymentMethodSerializer(serializers.ModelSerializer):
    new_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = PaymentMethod
        fields = (
            'id',
            'name',
            'new_name',
            'is_active',
            'created_at',
            'updated_at',
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'is_active': {'required': False},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
        }

    def validate(self, data):
        name = data.get('name')
        new_name = data.get('new_name')

        if new_name:
            if PaymentMethod.objects.filter(name=new_name).exclude(name=name).exists():
                raise serializers.ValidationError(
                    {'new_name': 'Ya existe un método de pago con ese nombre.'}
                )

        return data

    def update(self, instance, validated_data):
        new_name = validated_data.pop('new_name', None)
        if new_name:
            validated_data.pop('name', None)
            instance.name = new_name
        return super().update(instance, validated_data)
