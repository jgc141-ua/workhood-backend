from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.views import BenefitsViewSet, MembershipTypesViewSet, MembersViewSet, ResourcesViewSet, ResourceTypesViewSet, UserViewSet

urlpatterns = [
    #path("admin/", admin.site.urls),
    path("accounts/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accounts/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("accounts/me/", UserViewSet.as_view({"get": "me"}), name="user_me"),
    path("accounts/me/update/", UserViewSet.as_view({"put": "update", "patch": "update"}), name="user_update"),
    path("accounts/signup/", UserViewSet.as_view({"post": "signup"}), name="user_signup"),
    path("members/all/", MembersViewSet.as_view({"get": "list"}), name="members_list"),
    path("members/delete/", MembersViewSet.as_view({"delete": "delete"}), name="members_delete"),
    path("members/<str:email>/", MembersViewSet.as_view({"get": "retrieve", "put": "update", "patch": "update"}), name="admin_member_detail"),
    path("membership-types/all/", MembershipTypesViewSet.as_view({"get": "all"}), name="all_membership_types"),
    path("membership-types/active/", MembershipTypesViewSet.as_view({"get": "active"}), name="active_membership_types"),
    path("membership-types/create/", MembershipTypesViewSet.as_view({"post": "create"}), name="create_membership_type"),
    path("membership-types/update/", MembershipTypesViewSet.as_view({"put": "update", "patch": "update"}), name="update_membership_type"),
    path("membership-types/delete/", MembershipTypesViewSet.as_view({"delete": "delete"}), name="delete_membership_type"),
    path("benefits/all/", BenefitsViewSet.as_view({"get": "all"}), name="all_benefits"),
    path("benefits/create/", BenefitsViewSet.as_view({"post": "create"}), name="create_benefit"),
    path("benefits/update/", BenefitsViewSet.as_view({"put": "update", "patch": "update"}), name="update_benefit"),
    path("benefits/delete/", BenefitsViewSet.as_view({"delete": "delete"}), name="delete_benefit"),
    path("resource-types/all/", ResourceTypesViewSet.as_view({"get": "all"}), name="all_resource_types"),
    path("resource-types/create/", ResourceTypesViewSet.as_view({"post": "create"}), name="create_resource_type"),
    path("resource-types/update/", ResourceTypesViewSet.as_view({"put": "update", "patch": "update"}), name="update_resource_type"),
    path("resource-types/delete/", ResourceTypesViewSet.as_view({"delete": "delete"}), name="delete_resource_type"),
    path("resources/all/", ResourcesViewSet.as_view({"get": "all"}), name="all_resources"),
    path("resources/create/", ResourcesViewSet.as_view({"post": "create"}), name="create_resource"),
    path("resources/update/", ResourcesViewSet.as_view({"put": "update", "patch": "update"}), name="update_resource"),
    path("resources/delete/", ResourcesViewSet.as_view({"delete": "delete"}), name="delete_resource"),
]
