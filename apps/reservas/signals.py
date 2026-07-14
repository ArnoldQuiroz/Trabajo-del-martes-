from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Reserva

@receiver(post_save, sender=Reserva)
def notificar_cambio_reserva(sender, instance, created, **kwargs):
    """
    Dispara una notificación por WebSocket cuando 
    hay cambios críticos en la reserva o es nueva.
    """
    if created or instance.estado in ['CONFIRMADA', 'CANCELADA', 'REPROGRAMADA', 'EN_MESA', 'NO_ASISTIO']:
        channel_layer = get_channel_layer()
        mesa_str = instance.mesa.numero if instance.mesa else "TBD"
        accion = "Nueva Reserva" if created else f"Reserva {instance.estado}"
        
        try:
            async_to_sync(channel_layer.group_send)(
                "notificaciones_mozos",
                {
                    # Usamos el type existente notify_ready 
                    # para que el toast de UI lo atrape sin modificar Alpine
                    "type": "notify_ready", 
                    "mesa": mesa_str,
                    "cliente": instance.cliente_nombre,
                    "plato": f"{accion} - {instance.hora.strftime('%H:%M')}",
                }
            )
        except Exception as e:
            print(f"Error WebSocket notificar_cambio_reserva: {e}", flush=True)
