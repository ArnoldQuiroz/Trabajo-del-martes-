from django.contrib import admin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombres', 'apellidos', 'tipo_documento', 'numero_documento', 'telefono', 'activo')
    list_filter = ('activo', 'tipo_documento')
    search_fields = ('nombres', 'apellidos', 'numero_documento', 'email')
    ordering = ('-fecha_registro',)
