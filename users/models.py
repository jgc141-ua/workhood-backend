from django.contrib.auth.models import AbstractUser
from django.db import models

# Address model to store user addresses
class Address(models.Model):
    id = models.AutoField(primary_key=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

# Role model to define user roles
class Role(models.Model):
    id = models.AutoField(primary_key=True)

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

    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)

# Custom user model extending AbstractUser
class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    
    # Fields
    nif_cif = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Relationship
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='address')
    billing_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='billing_address')
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='role')

    # Set email as the USERNAME_FIELD for authentication
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

# Legal model to store user legal agreements
class Legal(models.Model):
    id = models.AutoField(primary_key=True)
    terms = models.BooleanField(default=False)
    terms_date = models.DateTimeField(null=False, blank=False)
    privacy = models.BooleanField(default=False)
    privacy_date = models.DateTimeField(null=False, blank=False)
    marketing = models.BooleanField(default=False)
    marketing_date = models.DateTimeField(null=True, blank=True)

    # Relationship
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='user_legal')

# Invoice model to store user invoices
class Invoice(models.Model):
    id = models.AutoField(primary_key=True)
    invoice_number = models.CharField(max_length=50, unique=True)
    concept = models.CharField(max_length=255)
    tax_base = models.DecimalField(max_digits=10, decimal_places=2)
    iva = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    issue_date = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=20, default='Pending')

    # Relationship
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='user_invoices')

# Payment model to store invoice payments
class Payment(models.Model):
    id = models.AutoField(primary_key=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=50)
    payment_date = models.DateTimeField(auto_now_add=True)

    # Relationship
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='invoice_payments')

# Membership_Type model to define different membership types and their benefits
class Membership_Type(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(max_length=100, blank=True)
    monthly_price = models.DecimalField(max_digits=6, decimal_places=2)
    is_fixed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

# Resource_Type model to define different types of resources available for reservation
class Resource_Type(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

# Benefit model to define benefits associated with membership types
class Benefit(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(blank=True, null=True, help_text="Cantidad incluida. Null = ilimitado.")
    is_active = models.BooleanField(default=True)

    # Relationships
    resource_type = models.ForeignKey(Resource_Type, on_delete=models.PROTECT, related_name='benefits', null=True, blank=True)
    membership_type = models.ManyToManyField(Membership_Type, related_name='membership_type_benefits')

# Resource model to define resources that can be reserved by users
class Resource(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    capacity = models.IntegerField()
    availability = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    # Relationship
    resource_type = models.ForeignKey(Resource_Type, on_delete=models.PROTECT, related_name='resource_type')

# Membership model to store user memberships and their associated resources
class Membership(models.Model):
    id = models.AutoField(primary_key=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Relationship
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='user_membership')
    membership_type = models.ForeignKey(Membership_Type, on_delete=models.PROTECT, related_name='membership_type')
    resource = models.OneToOneField(Resource, on_delete=models.SET_NULL, related_name='membership_resources', null=True, blank=True)

# Reservation model to store user reservations for resources
class Reservation(models.Model):
    id = models.AutoField(primary_key=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    state = models.CharField(max_length=20, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    # Relationship
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='user_reservations')
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='resource_reservations')
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name='membership_reservations')