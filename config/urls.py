from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.views import MembershipTypesViewSet, MembersViewSet, UserViewSet

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
]