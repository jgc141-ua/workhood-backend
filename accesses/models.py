from django.db import models

from users.models import CustomUser, Membership

# region Access
class Access(models.Model):
    ENTRADA = 'ENTRADA'
    SALIDA = 'SALIDA'
    EVENT_TYPE = [
        (ENTRADA, 'Entrada'),
        (SALIDA, 'Salida'),
    ]

    PERMITIDO = 'PERMITIDO'
    DENEGADO = 'DENEGADO'
    RESULT = [
        (PERMITIDO, 'Permitido'),
        (DENEGADO, 'Denegado'),
    ]

    id = models.AutoField(primary_key=True)
    event = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=EVENT_TYPE)
    result = models.CharField(max_length=10, choices=RESULT)

    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name='registros_acceso')
    user_name = models.CharField(max_length=255)
    user_email = models.EmailField()
    user_nif_cif = models.CharField(max_length=20, blank=True, null=True)

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name='registros_acceso', null=True, blank=True)
