from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView
from users.views import BenefitsViewSet, MembershipsViewSet, MembershipTypesViewSet, MembersViewSet, ResourcesViewSet, ResourceTypesViewSet, UserViewSet, CustomTokenRefreshView
from reservations.views import ReservationsViewSet, SpaceScheduleViewSet
from accesses.views import AccessViewSet
from invoices_payments.views import InvoicesAdminViewSet, InvoicesMemberViewSet, PaymentMethodsViewSet

# Rutas principales de la API de WorkHood
urlpatterns = [
    # region Accounts
    # Autenticación y gestión del perfil del usuario
    path("accounts/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accounts/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("accounts/me/", UserViewSet.as_view({"get": "me"}), name="user_me"),
    path("accounts/me/update/", UserViewSet.as_view({"put": "update", "patch": "update"}), name="user_update"),
    path("accounts/signup/", UserViewSet.as_view({"post": "signup"}), name="user_signup"),

    # region Members
    # Administración de miembros por parte del operador
    path("members/all/", MembersViewSet.as_view({"get": "list"}), name="members_list"),
    path("members/delete/", MembersViewSet.as_view({"delete": "delete"}), name="members_delete"),
    path("members/<str:email>/", MembersViewSet.as_view({"get": "retrieve", "put": "update", "patch": "update"}), name="admin_member_detail"),

    # region MembershipTypes
    # Gestión de tipos de membresía
    path("membership-types/all/", MembershipTypesViewSet.as_view({"get": "all"}), name="all_membership_types"),
    path("membership-types/active/", MembershipTypesViewSet.as_view({"get": "active"}), name="active_membership_types"),
    path("membership-types/create/", MembershipTypesViewSet.as_view({"post": "create"}), name="create_membership_type"),
    path("membership-types/update/", MembershipTypesViewSet.as_view({"put": "update", "patch": "update"}), name="update_membership_type"),
    path("membership-types/delete/", MembershipTypesViewSet.as_view({"delete": "delete"}), name="delete_membership_type"),

    # region Memberships
    # Operaciones sobre membresías de usuarios
    path("memberships/my-membership/", MembershipsViewSet.as_view({"get": "my_membership"}), name="my_membership"),
    path("memberships/my-toggle-auto-renew/", MembershipsViewSet.as_view({"post": "my_toggle_auto_renew"}), name="my_toggle_auto_renew"),
    path("memberships/available-resources/", MembershipsViewSet.as_view({"get": "available_resources"}), name="available_resources"),
    path("memberships/subscribe/", MembershipsViewSet.as_view({"post": "subscribe"}), name="subscribe"),
    path("memberships/member-membership/", MembershipsViewSet.as_view({"get": "member_membership"}), name="member_membership"),
    path("memberships/subscribe-member/", MembershipsViewSet.as_view({"post": "subscribe_member"}), name="subscribe_member"),
    path("memberships/cancel-membership/", MembershipsViewSet.as_view({"post": "cancel_membership"}), name="cancel_membership"),
    path("memberships/toggle-auto-renew/", MembershipsViewSet.as_view({"post": "toggle_auto_renew"}), name="toggle_auto_renew"),

    # region Benefits
    # Gestión de beneficios incluidos en membresías
    path("benefits/all/", BenefitsViewSet.as_view({"get": "all"}), name="all_benefits"),
    path("benefits/create/", BenefitsViewSet.as_view({"post": "create"}), name="create_benefit"),
    path("benefits/update/", BenefitsViewSet.as_view({"put": "update", "patch": "update"}), name="update_benefit"),
    path("benefits/delete/", BenefitsViewSet.as_view({"delete": "delete"}), name="delete_benefit"),

    # region ResourceTypes
    # Gestión de categorías de recursos
    path("resource-types/all/", ResourceTypesViewSet.as_view({"get": "all"}), name="all_resource_types"),
    path("resource-types/create/", ResourceTypesViewSet.as_view({"post": "create"}), name="create_resource_type"),
    path("resource-types/update/", ResourceTypesViewSet.as_view({"put": "update", "patch": "update"}), name="update_resource_type"),
    path("resource-types/delete/", ResourceTypesViewSet.as_view({"delete": "delete"}), name="delete_resource_type"),

    # region Resources
    # Gestión de recursos concretos
    path("resources/all/", ResourcesViewSet.as_view({"get": "all"}), name="all_resources"),
    path("resources/create/", ResourcesViewSet.as_view({"post": "create"}), name="create_resource"),
    path("resources/update/", ResourcesViewSet.as_view({"put": "update", "patch": "update"}), name="update_resource"),
    path("resources/delete/", ResourcesViewSet.as_view({"delete": "delete"}), name="delete_resource"),

    # region Reservations
    # Reservas de recursos por parte de los miembros
    path("reservations/my/", ReservationsViewSet.as_view({"get": "my_reservations"}), name="my_reservations"),
    path("reservations/all/", ReservationsViewSet.as_view({"get": "all_reservations"}), name="all_reservations"),
    path("reservations/create/", ReservationsViewSet.as_view({"post": "create_reservation"}), name="create_reservation"),
    path("reservations/cancel/", ReservationsViewSet.as_view({"post": "cancel_reservation"}), name="cancel_reservation"),
    path("reservations/availability/", ReservationsViewSet.as_view({"get": "availability"}), name="availability"),
    path("reservations/resource-schedule/", ReservationsViewSet.as_view({"get": "resource_schedule"}), name="resource_schedule"),

    # Horarios del espacio (gestión admin)
    path("space-schedule/all/", SpaceScheduleViewSet.as_view({"get": "all"}), name="all_space_schedules"),
    path("space-schedule/create/", SpaceScheduleViewSet.as_view({"post": "create"}), name="create_space_schedule"),
    path("space-schedule/update/", SpaceScheduleViewSet.as_view({"put": "update", "patch": "update"}), name="update_space_schedule"),
    path("space-schedule/delete/", SpaceScheduleViewSet.as_view({"delete": "delete"}), name="delete_space_schedule"),

    # region Accesses
    # Control de accesos del espacio
    path("accesses/check-in/", AccessViewSet.as_view({"post": "check_in"}), name="access_check_in"),
    path("accesses/check-out/", AccessViewSet.as_view({"post": "check_out"}), name="access_check_out"),
    path("accesses/logs/", AccessViewSet.as_view({"get": "logs"}), name="access_logs"),
    path("accesses/my-logs/", AccessViewSet.as_view({"get": "my_logs"}), name="access_my_logs"),

    # region PaymentMethods
    # Gestión de métodos de pago
    path("payment-methods/all/", PaymentMethodsViewSet.as_view({"get": "all"}), name="all_payment_methods"),
    path("payment-methods/create/", PaymentMethodsViewSet.as_view({"post": "create"}), name="create_payment_method"),
    path("payment-methods/update/", PaymentMethodsViewSet.as_view({"put": "update", "patch": "update"}), name="update_payment_method"),
    path("payment-methods/delete/", PaymentMethodsViewSet.as_view({"delete": "delete"}), name="delete_payment_method"),

    # region Invoices
    # Facturas del miembro
    path("invoices/my/", InvoicesMemberViewSet.as_view({"get": "my"}), name="my_invoices"),
    path("invoices/my-detail/", InvoicesMemberViewSet.as_view({"get": "my_detail"}), name="my_invoice_detail"),
    path("invoices/pay/", InvoicesMemberViewSet.as_view({"post": "pay"}), name="pay_invoice"),
    # Facturas del operador
    path("invoices/all/", InvoicesAdminViewSet.as_view({"get": "all"}), name="all_invoices"),
    path("invoices/invoice-detail/", InvoicesAdminViewSet.as_view({"get": "invoice_detail"}), name="admin_invoice_detail"),
    path("invoices/issue/", InvoicesAdminViewSet.as_view({"post": "issue"}), name="admin_invoice_issue"),
    path("invoices/register-payment/", InvoicesAdminViewSet.as_view({"post": "register_payment"}), name="register_payment"),
    path("invoices/cancel/", InvoicesAdminViewSet.as_view({"post": "cancel"}), name="cancel_invoice"),
]
