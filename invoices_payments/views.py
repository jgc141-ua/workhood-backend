from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsOperatorAdmin

from .models import PaymentMethod
from .serializers import PaymentMethodSerializer


# region PaymentMethod
class PaymentMethodsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentMethod.objects.all()

    @action(detail=False, methods=['get'], url_path='all', permission_classes=[IsOperatorAdmin])
    def all(self, request):
        queryset = self.get_queryset().order_by('name')
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='create', permission_classes=[IsOperatorAdmin])
    def create(self, request):
        serializer = PaymentMethodSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['put', 'patch'], url_path='update', permission_classes=[IsOperatorAdmin])
    def update(self, request):
        name = request.data.get('name')
        if not name:
            return Response(
                {'detail': "El campo 'name' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_method = PaymentMethod.objects.get(name=name)
        except PaymentMethod.DoesNotExist:
            return Response(
                {'detail': 'Método de pago no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PaymentMethodSerializer(payment_method, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['delete'], url_path='delete', permission_classes=[IsOperatorAdmin])
    def delete(self, request):
        name = request.data.get('name')
        if not name:
            return Response(
                {'detail': "El campo 'name' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_method = PaymentMethod.objects.get(name=name)
        except PaymentMethod.DoesNotExist:
            return Response(
                {'detail': 'Método de pago no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payment_method.delete()
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar el método de pago porque tiene pagos asociados.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {'detail': 'Método de pago eliminado correctamente.'},
            status=status.HTTP_204_NO_CONTENT,
        )
