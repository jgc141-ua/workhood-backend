from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

import re


# Expresiones regulares para validación de campos
POSTAL_CODE_REGEX = r"^\d{5}$"
EMAIL_REGEX = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
PASSWORD_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$"
PHONE_REGEX = r"^\+(\d{1,4})\s(\d{9,15})$"
NIF_REGEX = r"^\d{8}[A-HJ-NP-TV-Z]$"
NIE_REGEX = r"^[XYZ]\d{7}[A-Z]$"
CIF_REGEX = r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$"


def validate_email_format(value):
    """Valida que el email tenga un formato correcto y lo devuelve limpio."""
    cleaned = value.strip().lower()
    if not re.fullmatch(EMAIL_REGEX, cleaned):
        raise serializers.ValidationError("El email no tiene un formato válido.")
    return cleaned


def validate_phone_format(phone):
    """Valida que el teléfono tenga un formato correcto y lo devuelve limpio."""
    if not phone:
        return phone
    if not re.fullmatch(PHONE_REGEX, phone):
        raise serializers.ValidationError("El teléfono no tiene un formato válido.")
    return phone


def validate_password_strength(value):
    """Valida que la contraseña cumpla los requisitos de seguridad."""
    if not re.fullmatch(PASSWORD_REGEX, value):
        raise serializers.ValidationError(
            "La contraseña debe tener al menos 8 caracteres, una letra, un número y un símbolo."
        )
    try:
        django_validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return value


def validate_nif_cif_format(value):
    """Valida que el NIF/CIF/NIE sea obligatorio y tenga un formato correcto."""
    if not value:
        raise serializers.ValidationError("El NIF/CIF/NIE es obligatorio.")

    cleaned = value.strip().upper()

    if re.fullmatch(NIF_REGEX, cleaned) or re.fullmatch(NIE_REGEX, cleaned) or re.fullmatch(CIF_REGEX, cleaned):
        return cleaned

    raise serializers.ValidationError("NIF/NIE/CIF no válido.")


def validate_postal_code_format(value):
    """Valida que el código postal contenga exactamente 5 dígitos."""
    if value and not re.fullmatch(POSTAL_CODE_REGEX, value):
        raise serializers.ValidationError("El código postal debe contener solo 5 dígitos.")
    return value


def validate_min_length(value, min_length=3, message=None, field_name=None):
    """Valida que un campo de texto tenga una longitud mínima."""
    default_message = f"El campo debe contener al menos {min_length} caracteres."
    if value and len(value) < min_length:
        error_message = message or default_message
        if field_name:
            raise serializers.ValidationError({field_name: error_message})
        raise serializers.ValidationError(error_message)
    return value
