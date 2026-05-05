from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Address, Benefit, CustomUser, Role, Legal, Membership_Type
from .utils.validators import (
    validate_email_format,
    validate_phone_format,
    validate_password_strength,
    validate_nif_cif_format,
    validate_postal_code_format,
    validate_min_length,
)

User = get_user_model()

# region Address
class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["street", "city", "state", "postal_code", "country"]

    def validate(self, data):
        for field in ["street", "city", "state", "country"]:
            validate_min_length(data.get(field), min_length=3, field_name=field)
        validate_postal_code_format(data.get("postal_code"))
        return data


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["name"]
        extra_kwargs = {
            'name': {'validators': []}
        }

    def validate_name(self, value):
        allowed = {choice[0] for choice in Role.ROLE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("Rol no válido.")
        return value


class LegalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Legal
        fields = ["terms", "terms_date", "privacy", "privacy_date", "marketing", "marketing_date"]

    def validate(self, attrs):
        if "terms" in attrs and not attrs.get("terms", False):
            raise serializers.ValidationError({"terms": "Debes aceptar los términos y condiciones."})
        if "privacy" in attrs and not attrs.get("privacy", False):
            raise serializers.ValidationError({"privacy": "Debes aceptar la política de privacidad."})
        if "terms_date" in attrs and not attrs.get("terms_date", None):
            raise serializers.ValidationError({"terms_date": "Debes mencionar la fecha en la que se acepto los términos y condiciones"})
        if "privacy_date" in attrs and not attrs.get("privacy_date", None):
            raise serializers.ValidationError({"privacy_date": "Debes mencionar la fecha en la que se acepto la política de privacidad"})
        return attrs

# region User
class UserSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
    billing_address = AddressSerializer()
    role = RoleSerializer()
    user_legal = LegalSerializer()

    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nif_cif = serializers.CharField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password_confirm = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "nif_cif",
            "password",
            "password_confirm",
            "address",
            "billing_address",
            "role",
            "user_legal",
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["billing_same_as_address"] = instance.address_id == instance.billing_address_id
        return ret

    def validate_email(self, value):
        return validate_email_format(value)

    def validate_phone(self, value):
        return validate_phone_format(value)

    def validate_password(self, value):
        if not value:
            return value
        return validate_password_strength(value)

    def validate_nif_cif(self, value):
        return validate_nif_cif_format(value)

    def validate(self, data):
        validate_min_length(
            data.get("first_name", "").strip(),
            min_length=2,
            field_name="first_name",
            message="El nombre debe tener al menos 2 caracteres.",
        )
        validate_min_length(
            data.get("last_name", "").strip(),
            min_length=2,
            field_name="last_name",
            message="Los apellidos deben tener al menos 2 caracteres.",
        )
        password = data.get("password")
        password_confirm = data.get("password_confirm")
        if password or password_confirm:
            if password != password_confirm:
                raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
            if not password:
                raise serializers.ValidationError({"password": "Debes introducir la contraseña."})
        if self.initial_data.get("billing_same_as_address"):
            data.pop("billing_address", None)
        return data

    def pop_validated_data(self, validated_data):
        address_data = validated_data.pop("address", None)
        billing_address_data = validated_data.pop("billing_address", None)
        billing_same_as_address = self.initial_data.get("billing_same_as_address", False)
        role_data = validated_data.pop("role", None)
        legal_data = validated_data.pop("user_legal", None)
        password = validated_data.pop("password", None) or None
        validated_data.pop("password_confirm", None)
        return address_data, billing_address_data, billing_same_as_address, role_data, legal_data, password

    @transaction.atomic
    def create(self, validated_data):
        address_data, billing_address_data, billing_same_as_address, role_data, legal_data, password = self.pop_validated_data(validated_data)

        if not address_data:
            raise serializers.ValidationError({"address": "Este campo es obligatorio."})
        if not role_data:
            raise serializers.ValidationError({"role": "Este campo es obligatorio."})
        if not legal_data:
            raise serializers.ValidationError({"user_legal": "Este campo es obligatorio."})

        address = Address.objects.create(**address_data)
        if billing_same_as_address:
            billing_address = address
        else:
            billing_address = Address.objects.create(**billing_address_data) if billing_address_data else None

        role, _ = Role.objects.get_or_create(name=role_data["name"])

        user = User.objects.create(
            address=address,
            billing_address=billing_address,
            role=role,
            **validated_data
        )
        if password:
            user.set_password(password)
            user.save()

        Legal.objects.create(user=user, **legal_data)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        address_data, billing_address_data, billing_same_as_address, _, legal_data, password = self.pop_validated_data(validated_data)

        # Eliminar role de validated_data para evitar actualización
        validated_data.pop("role", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        if address_data:
            if instance.address:
                for attr, value in address_data.items():
                    setattr(instance.address, attr, value)
                instance.address.save()
            else:
                instance.address = Address.objects.create(**address_data)

        if billing_same_as_address:
            instance.billing_address = instance.address
        elif billing_address_data:
            # Si billing_address era la misma instancia que address, creamos una nueva
            if instance.billing_address_id == instance.address_id:
                instance.billing_address = Address.objects.create(**billing_address_data)
            elif instance.billing_address:
                for attr, value in billing_address_data.items():
                    setattr(instance.billing_address, attr, value)
                instance.billing_address.save()
            else:
                instance.billing_address = Address.objects.create(**billing_address_data)

        instance.save()

        if legal_data and hasattr(instance, "user_legal"):
            legal = instance.user_legal
            if "marketing" in legal_data:
                legal.marketing = legal_data["marketing"]
                legal.marketing_date = timezone.now()
                legal.save(update_fields=["marketing", "marketing_date"])

        return instance

# region Member
class MemberListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "id",
            "nif_cif",
            "first_name",
            "last_name",
            "email",
            "phone",
        )


class AdminMemberDetailSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
    billing_address = AddressSerializer()

    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nif_cif = serializers.CharField()

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "nif_cif",
            "address",
            "billing_address",
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["billing_same_as_address"] = instance.address_id == instance.billing_address_id
        return ret

    def validate_email(self, value):
        return validate_email_format(value)

    def validate_phone(self, value):
        return validate_phone_format(value)

    def validate_nif_cif(self, value):
        return validate_nif_cif_format(value)

    def validate(self, data):
        validate_min_length(
            data.get("first_name", "").strip(),
            min_length=2,
            field_name="first_name",
            message="El nombre debe tener al menos 2 caracteres.",
        )
        validate_min_length(
            data.get("last_name", "").strip(),
            min_length=2,
            field_name="last_name",
            message="Los apellidos deben tener al menos 2 caracteres.",
        )
        if self.initial_data.get("billing_same_as_address"):
            data.pop("billing_address", None)
        return data

    def update(self, instance, validated_data):
        address_data = validated_data.pop("address", None)
        billing_address_data = validated_data.pop("billing_address", None)
        billing_same_as_address = self.initial_data.get("billing_same_as_address", False)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if address_data:
            if instance.address:
                for attr, value in address_data.items():
                    setattr(instance.address, attr, value)
                instance.address.save()
            else:
                instance.address = Address.objects.create(**address_data)

        if billing_same_as_address:
            instance.billing_address = instance.address
        elif billing_address_data:
            if instance.billing_address_id == instance.address_id:
                instance.billing_address = Address.objects.create(**billing_address_data)
            elif instance.billing_address:
                for attr, value in billing_address_data.items():
                    setattr(instance.billing_address, attr, value)
                instance.billing_address.save()
            else:
                instance.billing_address = Address.objects.create(**billing_address_data)

        instance.save()
        return instance

# region MembershipType
class MembershipTypeSerializer(serializers.ModelSerializer):
    new_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Membership_Type
        fields = (
            "id",
            "name",
            "new_name",
            "description",
            "monthly_price",
            "is_fixed",
            "is_active",
        )
        
        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
            'monthly_price': {'required': False},
            'is_fixed': {'required': False},
            'is_active': {'required': False},
        }

    def validate(self, data):
        name = data.get('name')
        new_name = data.get('new_name')

        if new_name:
            if Membership_Type.objects.filter(name=new_name).exclude(name=name).exists():
                raise serializers.ValidationError({"new_name": "Ya existe un tipo de membresía con ese nombre."})
        return data

    def update(self, instance, validated_data):
        new_name = validated_data.pop('new_name', None)
        if new_name:
            validated_data.pop('name', None)
            instance.name = new_name
        return super().update(instance, validated_data)


# region Benefit
class BenefitSerializer(serializers.ModelSerializer):
    new_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Benefit
        fields = (
            "id",
            "name",
            "new_name",
            "description",
            "quantity",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
            'quantity': {'required': False},
        }

    def validate(self, data):
        name = data.get('name')
        new_name = data.get('new_name')

        if new_name:
            if Benefit.objects.filter(name=new_name).exclude(name=name).exists():
                raise serializers.ValidationError({"new_name": "Ya existe un beneficio con ese nombre."})
        return data

    def update(self, instance, validated_data):
        new_name = validated_data.pop('new_name', None)
        if new_name:
            validated_data.pop('name', None)
            instance.name = new_name
        return super().update(instance, validated_data)
