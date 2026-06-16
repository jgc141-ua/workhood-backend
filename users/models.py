from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from .managers import SoftDeleteModel, SoftDeleteManager, SoftDeleteUserManager


# region Address
class Address(models.Model):
    id = models.AutoField(primary_key=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)


# region User
class CustomUser(AbstractUser, SoftDeleteModel):
    username = None
    email = models.EmailField(unique=True)

    nif_cif = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    ADMIN = 'ADMIN'
    MIEMBRO = 'MIEMBRO'
    MIEMBRO_ITINERANTE = 'MIEMBRO_ITINERANTE'
    VISITANTE = 'VISITANTE'
    ROLE_CHOICES = [
        (ADMIN, 'Operador'),
        (MIEMBRO, 'Miembro'),
        (MIEMBRO_ITINERANTE, 'Miembro Itinerante'),
        (VISITANTE, 'Visitante'),
    ]
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default=MIEMBRO_ITINERANTE)

    # Fechas de control
    updated_at = models.DateTimeField(auto_now=True)

    # Relaciones
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='address')
    billing_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='billing_address')

    # Convertir el campo de usuario en el email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = SoftDeleteUserManager()
    all_objects = models.Manager()


# region Legal
class Legal(models.Model):
    id = models.AutoField(primary_key=True)
    terms = models.BooleanField(default=False)
    terms_date = models.DateTimeField(auto_now_add=True)
    privacy = models.BooleanField(default=False)
    privacy_date = models.DateTimeField(auto_now_add=True)
    marketing = models.BooleanField(default=False)
    marketing_date = models.DateTimeField(null=True, blank=True)

    # Relaciones
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='user_legal')


# region MembershipType
class Membership_Type(SoftDeleteModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25)
    description = models.TextField(max_length=50, blank=True)
    monthly_price = models.DecimalField(max_digits=8, decimal_places=2)
    is_fixed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(deleted_at__isnull=True),
                name='unique_active_membership_type_name',
            ),
        ]
        base_manager_name = 'all_objects'

    objects = SoftDeleteManager()
    all_objects = models.Manager()


# region ResourceType
class Resource_Type(SoftDeleteModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25)
    description = models.TextField(blank=True, null=True)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(deleted_at__isnull=True),
                name='unique_active_resource_type_name',
            ),
        ]
        base_manager_name = 'all_objects'

    objects = SoftDeleteManager()
    all_objects = models.Manager()


# region Benefit
class Benefit(SoftDeleteModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25)
    description = models.TextField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField(blank=True, null=True, help_text="Cantidad incluida. Null = ilimitado.")

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Relaciones
    resource_type = models.ForeignKey(Resource_Type, on_delete=models.PROTECT, related_name='benefits', null=True, blank=True)
    membership_type = models.ManyToManyField(Membership_Type, related_name='membership_type_benefits')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(deleted_at__isnull=True),
                name='unique_active_benefit_name',
            ),
        ]
        base_manager_name = 'all_objects'

    objects = SoftDeleteManager()
    all_objects = models.Manager()


# region Resource
class Resource(SoftDeleteModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25)
    description = models.TextField(blank=True, null=True)
    capacity = models.IntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    availability = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Relaciones
    resource_type = models.ForeignKey(Resource_Type, on_delete=models.PROTECT, related_name='resource_type')

    class Meta:
        base_manager_name = 'all_objects'

    objects = SoftDeleteManager()
    all_objects = models.Manager()


# region Membership
class Membership(models.Model):
    id = models.AutoField(primary_key=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=True)
    signed_at = models.DateTimeField(auto_now_add=True)

    # Relaciones
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='user_membership')
    membership_type = models.ForeignKey(Membership_Type, on_delete=models.PROTECT, related_name='membership_type')
    resource = models.ForeignKey(Resource, on_delete=models.SET_NULL, related_name='membership_resources', null=True, blank=True)
