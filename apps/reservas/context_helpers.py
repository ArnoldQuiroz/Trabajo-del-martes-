from apps.menu.models import Categoria


def menu_reserva_context():
    categorias = (
        Categoria.objects.filter(activo=True)
        .prefetch_related('platos')
        .order_by('orden', 'nombre')
    )
    return {'categorias_menu': categorias}
