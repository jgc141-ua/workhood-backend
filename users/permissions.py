from rest_framework.permissions import BasePermission


class IsOperatorAdmin(BasePermission):
    message = "Solo un operador administrador puede realizar esta acción."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role
            and request.user.role.name == "ADMIN"
        )