from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_reservas, name='lista_reservas'),
    path('crear/', views.crear_reserva, name='crear_reserva'),
    path('api/mesas-disponibles/', views.api_mesas_disponibles_reserva, name='api_mesas_disponibles_reserva'),
    path('api/verificar-no-show/', views.api_verificar_no_show, name='api_verificar_no_show'),
    path('<int:pk>/estado/', views.cambiar_estado_reserva, name='cambiar_estado_reserva'),
    path('<int:pk>/confirmar-pedido/', views.confirmar_pedido_reserva, name='confirmar_pedido_reserva'),
    path('<int:pk>/confirmar-llegada/', views.confirmar_llegada_reserva, name='confirmar_llegada_reserva'),
    path('<int:pk>/pagar/', views.pago_reserva, name='pago_reserva'),
    path('configuracion/', views.panel_configuracion, name='configuracion_reservas'),
]
