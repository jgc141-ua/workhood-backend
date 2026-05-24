from datetime import timedelta

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .models import Address, Benefit, CustomUser, Membership, Resource, Resource_Type, Legal, Membership_Type
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
        # Valida longitudes mínimas y formato del código postal
        for field in ["street", "city", "state", "country"]:
            validate_min_length(data.get(field), min_length=3, field_name=field)
        validate_postal_code_format(data.get("postal_code"))
        return data


class LegalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Legal
        fields = ["terms", "privacy", "marketing"]

    def validate(self, attrs):
        # Exige la aceptación de términos y privacidad
        if "terms" in attrs and not attrs.get("terms", False):
            raise serializers.ValidationError({"terms": "Debes aceptar los términos y condiciones."})
        if "privacy" in attrs and not attrs.get("privacy", False):
            raise serializers.ValidationError({"privacy": "Debes aceptar la política de privacidad."})
        return attrs


# region User
class UserSerializer(serializers.ModelSerializer):
    address = AddressSerializer()
    billing_address = AddressSerializer()
    role = serializers.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        required=False,
        allow_blank=True,
    )
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
        # Indica si la dirección de facturación coincide con la dirección principal
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
        # Validaciones de campos obligatorios y coincidencia de contraseñas
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
        if not legal_data:
            raise serializers.ValidationError({"user_legal": "Este campo es obligatorio."})

        # Crea la dirección principal y, si aplica, la de facturación
        address = Address.objects.create(**address_data)
        if billing_same_as_address:
            billing_address = address
        else:
            billing_address = Address.objects.create(**billing_address_data) if billing_address_data else None

        role_name = role_data if role_data else CustomUser.MIEMBRO

        if role_name not in {choice[0] for choice in CustomUser.ROLE_CHOICES}:
            raise serializers.ValidationError({"role": "Rol no válido."})

        user = User.objects.create(
            address=address,
            billing_address=billing_address,
            role=role_name,
            **validated_data
        )
        if password:
            user.set_password(password)
            user.save()

        # Registra la fecha de aceptación del marketing si procede
        legal_data["marketing_date"] = timezone.now() if legal_data.get("marketing") else None

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

        # Actualiza o crea la dirección principal
        if address_data:
            if instance.address:
                for attr, value in address_data.items():
                    setattr(instance.address, attr, value)
                instance.address.save()
            else:
                instance.address = Address.objects.create(**address_data)

        # Actualiza la dirección de facturación respetando si es la misma instancia
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

        # Actualiza únicamente la aceptación de marketing
        if legal_data and hasattr(instance, "user_legal"):
            legal = instance.user_legal
            if "marketing" in legal_data:
                legal.marketing = legal_data["marketing"]
                legal.marketing_date = timezone.now() if legal_data["marketing"] else None
                legal.save(update_fields=["marketing", "marketing_date"])

        return instance


# region Member
class MemberListSerializer(serializers.ModelSerializer):
    active_membership = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "nif_cif",
            "first_name",
            "last_name",
            "email",
            "phone",
            "active_membership",
        )

    def get_active_membership(self, obj):
        # Recupera la membresía activa más reciente del usuario
        memberships = getattr(obj, "active_memberships", None)
        if memberships:
            membership = memberships[0]
        else:
            membership = (
                obj.user_membership.filter(
                    is_active=True, end_date__gte=timezone.now()
                )
                .select_related("membership_type", "resource")
                .order_by("-start_date")
                .first()
            )

        if not membership:
            return None

        return {
            "id": membership.id,
            "membership_type_name": membership.membership_type.name,
            "resource_name": membership.resource.name if membership.resource else None,
            "end_date": membership.end_date,
        }


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

        # Actualiza la dirección principal
        if address_data:
            if instance.address:
                for attr, value in address_data.items():
                    setattr(instance.address, attr, value)
                instance.address.save()
            else:
                instance.address = Address.objects.create(**address_data)

        # Actualiza la dirección de facturación
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
    benefits = serializers.PrimaryKeyRelatedField(
        queryset=Benefit.objects.all(),
        many=True,
        required=False,
        source='membership_type_benefits',
    )
    benefit_details = serializers.SerializerMethodField()

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
            "benefits",
            "benefit_details",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
            'monthly_price': {'required': False},
            'is_fixed': {'required': False},
            'is_active': {'required': False},
            'benefits': {'required': False},
        }

    def get_benefit_details(self, obj):
        # Devuelve los detalles de los beneficios para lectura
        return [
            {"id": b.id, "name": b.name, "quantity": b.quantity}
            for b in obj.membership_type_benefits.all()
        ]

    def validate(self, data):
        # Evita duplicados al renombrar un tipo de membresía
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
    resource_type = serializers.PrimaryKeyRelatedField(
        queryset=Resource_Type.objects.all(),
        required=False,
        allow_null=True,
    )
    resource_type_name = serializers.CharField(source='resource_type.name', read_only=True)

    class Meta:
        model = Benefit
        fields = (
            "id",
            "name",
            "new_name",
            "description",
            "quantity",
            "resource_type",
            "resource_type_name",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
            'quantity': {'required': False},
            'resource_type': {'required': False},
        }

    def validate(self, data):
        # Evita duplicados al renombrar un beneficio
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


# region ResourceType
class ResourceTypeSerializer(serializers.ModelSerializer):
    new_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Resource_Type
        fields = (
            "id",
            "name",
            "new_name",
            "description",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
        }

    def validate(self, data):
        # Evita duplicados al renombrar un tipo de recurso
        name = data.get('name')
        new_name = data.get('new_name')

        if new_name:
            if Resource_Type.objects.filter(name=new_name).exclude(name=name).exists():
                raise serializers.ValidationError({"new_name": "Ya existe un tipo de recurso con ese nombre."})
        return data

    def update(self, instance, validated_data):
        new_name = validated_data.pop('new_name', None)
        if new_name:
            validated_data.pop('name', None)
            instance.name = new_name
        return super().update(instance, validated_data)


# region Resource
class ResourceSerializer(serializers.ModelSerializer):
    resource_type_name = serializers.CharField(source='resource_type.name', read_only=True)

    class Meta:
        model = Resource
        fields = (
            "id",
            "name",
            "description",
            "capacity",
            "price",
            "availability",
            "is_active",
            "resource_type",
            "resource_type_name",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'name': {'required': True},
            'description': {'required': False},
            'capacity': {'required': True},
            'price': {'required': False},
            'availability': {'required': False},
            'is_active': {'required': False},
            'resource_type': {'required': True},
        }

    def validate_capacity(self, value):
        # La capacidad debe ser al menos 1
        if value is not None and value < 1:
            raise serializers.ValidationError("La capacidad debe ser mayor que 0.")
        return value


# region Membership
class MembershipSerializer(serializers.ModelSerializer):
    membership_type_name = serializers.CharField(source='membership_type.name', read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id",
            "user",
            "membership_type",
            "membership_type_name",
            "resource",
            "resource_name",
            "price",
            "start_date",
            "end_date",
            "is_active",
            "auto_renew",
            "signed_at",
        )

        extra_kwargs = {
            'id': {'read_only': True},
            'user': {'read_only': True},
            'membership_type': {'required': True},
            'resource': {'required': False},
            'price': {'read_only': True},
            'start_date': {'read_only': True},
            'end_date': {'read_only': True},
            'is_active': {'read_only': True},
            'signed_at': {'read_only': True},
        }


class SubscribeSerializer(serializers.ModelSerializer):
    membership_type = serializers.PrimaryKeyRelatedField(
        queryset=Membership_Type.objects.filter(is_active=True)
    )

    resource = serializers.PrimaryKeyRelatedField(
        queryset=Resource.objects.all(),
        required=False,
        allow_null=True,
    )

    auto_renew = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Membership
        fields = ("membership_type", "resource", "auto_renew")

    def validate(self, data):
        # Comprueba que el usuario no tenga ya una membresía activa
        user = self.context.get("user")
        if not user:
            raise serializers.ValidationError("No se ha proporcionado un usuario.")

        membership_type = data.get("membership_type")
        resource = data.get("resource")

        active_membership = Membership.objects.filter(
            user=user,
            is_active=True,
            end_date__gte=timezone.now(),
        ).first()

        if active_membership:
            raise serializers.ValidationError("El usuario ya tiene una membresía activa.")

        # Valida el recurso en membresías con puesto fijo
        if membership_type.is_fixed:
            if not resource:
                raise serializers.ValidationError(
                    {"resource": "El recurso es obligatorio para membresías con recurso fijo."}
                )

            valid_resource_type_ids = set(
                Benefit.objects.filter(
                    membership_type=membership_type,
                    resource_type__isnull=False,
                ).values_list("resource_type", flat=True).distinct()
            )

            if not valid_resource_type_ids:
                raise serializers.ValidationError(
                    {"resource": "Este tipo de membresía no tiene configurado ningún tipo de recurso asignable."}
                )

            if resource.resource_type_id not in valid_resource_type_ids:
                raise serializers.ValidationError(
                    {"resource": "El recurso no es válido para este tipo de membresía."}
                )

            if Membership.objects.filter(
                is_active=True,
                resource=resource,
                end_date__gte=timezone.now(),
            ).exists():
                raise serializers.ValidationError(
                    {"resource": "El recurso seleccionado no está disponible."}
                )
        else:
            data["resource"] = None

        return data

    @transaction.atomic
    def create(self, validated_data):
        # Crea la membresía con una vigencia inicial de 30 días
        user = self.context.get("user")
        membership_type = validated_data["membership_type"]
        resource = validated_data.get("resource")

        start_date = timezone.now()
        end_date = start_date + timedelta(days=30)

        return Membership.objects.create(
            user=user,
            membership_type=membership_type,
            resource=resource,
            price=membership_type.monthly_price,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
            auto_renew=validated_data.get("auto_renew", True),
        )


class CancelMembershipSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    membership = serializers.SerializerMethodField(read_only=True)

    def validate_email(self, value):
        try:
            self.user = CustomUser.objects.get(email=value)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado.")
        return value

    def validate(self, data):
        # Verifica que el usuario tenga una membresía activa para cancelar
        user = getattr(self, "user", None)
        if not user:
            raise serializers.ValidationError("El campo 'email' es obligatorio.")

        membership = (
            Membership.objects.filter(user=user)
            .order_by("-start_date")
            .first()
        )

        if (
            not membership
            or not membership.is_active
            or not membership.end_date
            or membership.end_date <= timezone.now()
        ):
            raise serializers.ValidationError("El usuario no tiene una membresía activa.")

        self.membership = membership
        return data

    def get_membership(self, obj):
        return MembershipSerializer(self.membership).data

# region Token de refresco
# Gestión del token de refresco debido a error 500 generado con el serializer por defecto 
class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                "Usuario no encontrado.", code="user_not_found"
            )