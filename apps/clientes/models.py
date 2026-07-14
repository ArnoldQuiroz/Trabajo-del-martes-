from django.db import models
from django.conf import settings

class Cliente(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='perfil_cliente',
        verbose_name="Usuario Asociado"
    )
    TIPO_DOCUMENTO_CHOICES = [
        ('DNI', 'DNI'),
        ('RUC', 'RUC'),
        ('CE', 'Carné de Extranjería'),
        ('PASAPORTE', 'Pasaporte'),
    ]

    nombres = models.CharField(max_length=150, verbose_name="Nombres o Razón Social")
    apellidos = models.CharField(max_length=150, blank=True, null=True, verbose_name="Apellidos")
    tipo_documento = models.CharField(max_length=20, choices=TIPO_DOCUMENTO_CHOICES, default='DNI', verbose_name="Tipo de Documento")
    numero_documento = models.CharField(max_length=20, unique=True, verbose_name="Número de Documento")
    email = models.EmailField(max_length=150, blank=True, null=True, verbose_name="Correo Electrónico")
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = 'cliente'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        if self.apellidos:
            return f'{self.nombres} {self.apellidos} - {self.numero_documento}'
        return f'{self.nombres} - {self.numero_documento}'
