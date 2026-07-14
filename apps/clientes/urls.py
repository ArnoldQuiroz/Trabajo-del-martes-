from django.urls import path
from . import views

app_name = 'clientes'

urlpatterns = [
    path('registro/', views.registro_cliente, name='registro'),
    path('logout/', views.logout_cliente, name='logout'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('nueva-reserva/', views.nueva_reserva, name='nueva_reserva'),

    # Public pages
    path('', views.home_publica, name='home'),
    path('menu/', views.menu_publico, name='menu'),
    path('carrito/', views.carrito_publico, name='carrito'),
    path('checkout/', views.checkout_publico, name='checkout'),
]
