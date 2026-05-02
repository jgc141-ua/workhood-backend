from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.views import AdminMemberDetailAPIView, MembersListAPIView, UserViewSet

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accounts/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("accounts/me/", UserViewSet.as_view({"get": "me"}), name="user_me"),
    path("accounts/me/update/", UserViewSet.as_view({"put": "update", "patch": "update"}), name="user_update"),
    path("accounts/signup/", UserViewSet.as_view({"post": "signup"}), name="user_signup"),
    path("members/", MembersListAPIView.as_view(), name="members_list"),
    path("members/<str:email>/", AdminMemberDetailAPIView.as_view(), name="admin_member_detail"),
]