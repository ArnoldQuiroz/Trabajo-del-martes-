import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ReservasAdminConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            await self.channel_layer.group_add('reservas_admin_updates', self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('reservas_admin_updates', self.channel_name)

    async def reserva_update(self, event):
        await self.send(text_data=json.dumps({
            'action': event.get('action'),
            'detail': event.get('detail')
        }))
