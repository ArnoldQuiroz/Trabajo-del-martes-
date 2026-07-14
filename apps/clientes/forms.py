from django import forms

from apps.reservas.forms import ReservaForm
from apps.reservas.services import mesas_disponibles_para, parse_fecha_hora_form


class ClienteReservaForm(ReservaForm):
    class Meta(ReservaForm.Meta):
        fields = [
            'cliente_nombre',
            'cliente_telefono',
            'cliente_email',
            'fecha',
            'hora',
            'mesa',
            'cantidad_personas',
            'observaciones',
        ]

    def __init__(self, *args, cliente=None, **kwargs):
        self.cliente = cliente
        super().__init__(*args, **kwargs)

        self.fields['cliente_telefono'].required = True
        self.fields['mesa'].required = False
        self.fields['mesa'].widget.attrs['class'] = 'form-select rounded-xl p-3 reserva-mesa-input'

        fecha, hora = parse_fecha_hora_form(
            self.data.get('fecha') if self.data else None,
            self.data.get('hora') if self.data else None,
        )
        if fecha and hora:
            self.fields['mesa'].queryset = mesas_disponibles_para(fecha, hora)
            self.fields['mesa'].empty_label = 'Seleccione una mesa (opcional)'
        else:
            from apps.mesas.models import Mesa
            self.fields['mesa'].queryset = Mesa.objects.none()
            self.fields['mesa'].empty_label = 'Seleccione fecha y hora primero'

        self.fields['mesa'].label_from_instance = (
            lambda mesa: f"Mesa {mesa.numero} ({mesa.zona.nombre}) — {mesa.capacidad} pers."
        )

        if cliente and not self.is_bound:
            nombre = f"{cliente.nombres} {cliente.apellidos or ''}".strip()
            self.fields['cliente_nombre'].initial = nombre
            self.fields['cliente_email'].initial = cliente.email or ''
            if cliente.telefono:
                self.fields['cliente_telefono'].initial = cliente.telefono

        if cliente:
            self.fields['cliente_nombre'].widget.attrs['readonly'] = True
        self.fields['fecha'].widget.attrs.update({'class': 'form-control rounded-xl p-3 reserva-fecha-input'})
        self.fields['hora'].widget.attrs.update({'class': 'form-control rounded-xl p-3 reserva-hora-input'})

    def clean(self):
        cleaned_data = super().clean()
        mesa = cleaned_data.get('mesa')
        cantidad = cleaned_data.get('cantidad_personas')

        if mesa and cantidad and cantidad > mesa.capacidad:
            raise forms.ValidationError(
                f"La mesa {mesa.numero} tiene capacidad para {mesa.capacidad} personas."
            )

        return cleaned_data

    def save(self, commit=True):
        reserva = super().save(commit=False)
        cliente = self.cliente

        if cliente:
            reserva.cliente = cliente
            reserva.cliente_nombre = f"{cliente.nombres} {cliente.apellidos or ''}".strip()
            reserva.cliente_email = self.cleaned_data.get('cliente_email') or cliente.email

        reserva.estado = 'PENDIENTE'

        if commit:
            reserva.save()
            if cliente:
                cambios = []
                telefono = self.cleaned_data.get('cliente_telefono')
                email = self.cleaned_data.get('cliente_email')
                if telefono and cliente.telefono != telefono:
                    cliente.telefono = telefono
                    cambios.append('telefono')
                if email and cliente.email != email:
                    cliente.email = email
                    cambios.append('email')
                if cambios:
                    cliente.save(update_fields=cambios)

        return reserva
