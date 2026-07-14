"""
Servicios de negocio para el módulo Caja (versión completa CAJA).

Incluye:
- procesar_cobro(): procesamiento atómico de cobros, multi-pago, cobro parcial por líneas.
- registrar_perdida(): marcar una comanda como pérdida (no pagó).
"""
import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import CajaTurno, Pago, MetodoPago
from apps.mesas.models import Mesa
from apps.comandas.models import Comanda, LineaComanda


def _obtener_turno_activo():
    """Devuelve el CajaTurno abierto o lanza ValidationError."""
    turno = CajaTurno.objects.filter(estado=CajaTurno.Estado.ABIERTA).first()
    if not turno:
        raise ValidationError("No hay un turno de caja abierto. Abrí el turno antes de cobrar.")
    return turno


def _liberar_mesas_comanda(comanda):
    """Cambia todas las mesas de la comanda a estado LIMPIEZA y disuelve sus uniones."""
    from apps.mesas.models import UnionMesas
    from django.db.models import Q
    
    mesas = list(comanda.todas_las_mesas)
    
    # Buscar y eliminar uniones activas que incluyan a cualquiera de estas mesas
    uniones_activas = UnionMesas.objects.filter(
        Q(mesa_principal__in=mesas) | Q(mesas_secundarias__in=mesas),
        activa=True
    ).distinct()
    
    for union in uniones_activas:
        union.delete()
        
    # Cambiar estado de todas las mesas a LIMPIEZA
    for m in mesas:
        m.estado = Mesa.Estado.LIMPIEZA
        m.save(update_fields=['estado'])


def procesar_cobro(comanda_id, pagos_data, usuario, linea_ids=None, observacion=None):
    """
    Procesa el cobro de una comanda con soporte multi-pago.

    Args:
        comanda_id (int): ID de la comanda a cobrar.
        pagos_data (list): Lista de dicts con {metodo_pago_id, monto, referencia}.
                           Cada item puede ser un pago separado.
        usuario: El usuario que cobra.
        linea_ids (list[int]|None): Si se provee, solo cobra esas líneas (cobro parcial).
        observacion (str|None): Observación general del cobro.

    Returns:
        list[Pago]: Lista de pagos creados.
    """
    with transaction.atomic():
        turno = _obtener_turno_activo()

        try:
            comanda = Comanda.objects.select_for_update().get(pk=comanda_id)
        except Comanda.DoesNotExist:
            raise ValidationError("La comanda no existe.")

        if comanda.estado == Comanda.Estado.COBRADA:
            raise ValidationError("Esta comanda ya fue cobrada.")

        if comanda.estado not in [Comanda.Estado.LISTA, Comanda.Estado.ABIERTA]:
            raise ValidationError(
                f"La comanda no está disponible para cobrar. Estado: {comanda.get_estado_display()}"
            )

        # Líneas ya pagadas en cobros previos de la comanda
        lineas_ya_pagadas_ids = set(
            LineaComanda.objects.filter(
                comanda=comanda,
                pagos__estado=Pago.Estado.PAGADO
            ).values_list('id', flat=True)
        )

        # Determinar las líneas a cobrar
        if linea_ids:
            lineas = list(comanda.lineas.filter(pk__in=linea_ids).select_related('plato'))
        else:
            # Si no se especifican, se cobran todas las líneas activas que aún no han sido pagadas
            lineas = list(
                comanda.lineas.exclude(estado=LineaComanda.Estado.ANULADO)
                .exclude(id__in=lineas_ya_pagadas_ids)
                .select_related('plato')
            )

        if not lineas:
            raise ValidationError("No hay líneas válidas para cobrar.")

        # Validar que ninguna de las líneas que se quieren pagar ahora esté ya pagada
        lineas_ahora_ids = set(l.id for l in lineas)
        lineas_repetidas = lineas_ahora_ids.intersection(lineas_ya_pagadas_ids)
        if lineas_repetidas:
            nombres_repetidos = [l.plato.nombre for l in lineas if l.id in lineas_repetidas]
            raise ValidationError(
                f"Las siguientes líneas ya fueron pagadas: {', '.join(nombres_repetidos)}."
            )

        # Calcular el total a cobrar según las líneas seleccionadas
        total_a_cobrar = sum(l.subtotal for l in lineas)

        # Validar que la suma de los pagos cubra el total
        total_pagado = sum(Decimal(str(p.get('monto', 0))) for p in pagos_data)
        if total_pagado < total_a_cobrar:
            raise ValidationError(
                f"El monto total pagado (S/. {total_pagado}) es insuficiente para cubrir S/. {total_a_cobrar}."
            )

        # Generar un ID de transacción único para agrupar todos los pagos de este cobro
        transaccion_id = str(uuid.uuid4())[:8].upper()

        pagos_creados = []
        metodos_usados = []

        for i, p_data in enumerate(pagos_data):
            metodo = MetodoPago.objects.get(pk=p_data['metodo_pago_id'])
            monto_pago = Decimal(str(p_data.get('monto', 0)))

            # El vuelto solo aplica al último pago si hay uno solo o si el método lo permite
            if i == len(pagos_data) - 1:
                vuelto = max(Decimal('0'), total_pagado - total_a_cobrar) if metodo.permite_vuelto else Decimal('0')
            else:
                vuelto = Decimal('0')

            pago = Pago.objects.create(
                caja_turno=turno,
                comanda=comanda,
                metodo_pago=metodo,
                monto=monto_pago,
                vuelto=vuelto,
                referencia=p_data.get('referencia', ''),
                transaccion_id=transaccion_id,
                estado=Pago.Estado.PAGADO,
                observacion=p_data.get('observacion') or observacion or '',
            )

            # Asociar las líneas pagadas (M2M)
            pago.lineas_pagadas.set(lineas)
            pagos_creados.append(pago)
            metodos_usados.append(metodo)

        # Determinar si con este pago se completa toda la comanda
        lineas_activas = comanda.lineas.exclude(estado=LineaComanda.Estado.ANULADO)
        lineas_activas_ids = set(lineas_activas.values_list('id', flat=True))

        total_pagadas_ids = lineas_ya_pagadas_ids.union(lineas_ahora_ids)
        es_pago_completo = lineas_activas_ids.issubset(total_pagadas_ids)

        if es_pago_completo:
            # Si se completó el pago de toda la comanda, actualizar estado y liberar mesa
            comanda.estado = Comanda.Estado.COBRADA
            comanda.fecha_cierre = timezone.now()
            comanda.save(update_fields=['estado', 'fecha_cierre'])

            # Liberar mesas
            _liberar_mesas_comanda(comanda)

        # Actualizar totales del turno
        for i, pago in enumerate(pagos_creados):
            metodo = metodos_usados[i]
            turno.total_ventas += pago.monto
            if metodo.codigo == 'EFECTIVO':
                turno.total_efectivo += pago.monto
            else:
                turno.total_tarjeta += pago.monto

        turno.save(update_fields=['total_ventas', 'total_efectivo', 'total_tarjeta'])

        return pagos_creados


def _metodo_pago_desde_reserva(reserva_pago):
    codigo_map = {
        'YAPE': 'YAPE',
        'PLIN': 'YAPE',
        'TARJETA': 'TARJETA',
    }
    codigo = codigo_map.get(reserva_pago.metodo, 'YAPE')
    metodo = MetodoPago.objects.filter(codigo=codigo, activo=True).first()
    if not metodo:
        metodo = MetodoPago.objects.filter(activo=True).first()
    if not metodo:
        raise ValidationError('No hay métodos de pago configurados en caja.')
    return metodo


def _referencia_pago_reserva(reserva_pago):
    if reserva_pago.metodo in ('YAPE', 'PLIN') and reserva_pago.referencia:
        return reserva_pago.referencia.strip()
    if reserva_pago.metodo == 'TARJETA':
        partes = []
        if reserva_pago.titular_tarjeta:
            partes.append(reserva_pago.titular_tarjeta.strip())
        if reserva_pago.ultimos_digitos_tarjeta:
            partes.append(f"****{reserva_pago.ultimos_digitos_tarjeta.strip()}")
        return ' — '.join(partes) if partes else (reserva_pago.referencia or '')
    return reserva_pago.referencia or ''


def finalizar_comanda_reserva_prepagada(comanda_id, usuario):
    """Registra el pago de reserva en caja, genera boleta y cierra la comanda."""
    from apps.reservas.services import obtener_reserva_prepagada_comanda

    with transaction.atomic():
        turno = _obtener_turno_activo()

        try:
            comanda = Comanda.objects.select_for_update().get(pk=comanda_id)
        except Comanda.DoesNotExist:
            raise ValidationError("La comanda no existe.")

        reserva = obtener_reserva_prepagada_comanda(comanda)
        if not reserva or not hasattr(reserva, 'pago') or reserva.pago.estado != 'PAGADO':
            raise ValidationError("Esta comanda no tiene un pago anticipado de reserva.")

        lineas = list(
            comanda.lineas.exclude(estado=LineaComanda.Estado.ANULADO).select_related('plato')
        )
        if not lineas:
            raise ValidationError("La comanda no tiene platos para facturar.")

        if comanda.estado == Comanda.Estado.COBRADA:
            pago_existente = comanda.pagos.filter(estado=Pago.Estado.PAGADO).order_by('-id').first()
            if pago_existente:
                if not pago_existente.lineas_pagadas.exists():
                    pago_existente.lineas_pagadas.set(lineas)
                return pago_existente
            raise ValidationError("Esta comanda ya fue cobrada.")

        pago_existente = comanda.pagos.filter(estado=Pago.Estado.PAGADO).first()
        if pago_existente:
            if not pago_existente.lineas_pagadas.exists():
                pago_existente.lineas_pagadas.set(lineas)
            return pago_existente

        if not reserva.comanda_id:
            reserva.comanda = comanda
            reserva.save(update_fields=['comanda'])

        rp = reserva.pago
        metodo = _metodo_pago_desde_reserva(rp)
        total_lineas = sum(l.subtotal for l in lineas)
        monto_pago = rp.monto if rp.monto else total_lineas
        if total_lineas and abs(monto_pago - total_lineas) > Decimal('0.01'):
            monto_pago = total_lineas

        cliente = (reserva.cliente_nombre or comanda.nombre_cliente or '').strip()
        if cliente and comanda.nombre_cliente != cliente:
            comanda.nombre_cliente = cliente[:100]
            comanda.save(update_fields=['nombre_cliente'])

        pago = Pago.objects.create(
            caja_turno=turno,
            comanda=comanda,
            metodo_pago=metodo,
            monto=monto_pago,
            vuelto=Decimal('0'),
            referencia=_referencia_pago_reserva(rp),
            transaccion_id=str(uuid.uuid4())[:8].upper(),
            estado=Pago.Estado.PAGADO,
            observacion=cliente or f"Reserva #{reserva.id}",
        )
        pago.lineas_pagadas.set(lineas)

        comanda.estado = Comanda.Estado.COBRADA
        comanda.fecha_cierre = timezone.now()
        comanda.save(update_fields=['estado', 'fecha_cierre'])

        reserva.estado = 'FINALIZADA'
        reserva.save(update_fields=['estado', 'fecha_actualizacion'])

        _liberar_mesas_comanda(comanda)

        turno.total_ventas += pago.monto
        if metodo.codigo == 'EFECTIVO':
            turno.total_efectivo += pago.monto
        else:
            turno.total_tarjeta += pago.monto
        turno.save(update_fields=['total_ventas', 'total_efectivo', 'total_tarjeta'])

    return pago


def procesar_cobro_simple(comanda_id, metodo_pago_id, monto_recibido, usuario, referencia=None):
    """
    Wrapper legacy para cobros simples (un solo método de pago).
    Mantiene compatibilidad con código antiguo.
    """
    return procesar_cobro(
        comanda_id=comanda_id,
        pagos_data=[{'metodo_pago_id': metodo_pago_id, 'monto': monto_recibido, 'referencia': referencia}],
        usuario=usuario,
    )


def registrar_perdida(comanda_id, usuario, observacion):
    """
    Marca una comanda como pérdida (el cliente no pagó o se fue).
    """
    with transaction.atomic():
        turno = _obtener_turno_activo()

        try:
            comanda = Comanda.objects.select_for_update().get(pk=comanda_id)
        except Comanda.DoesNotExist:
            raise ValidationError("La comanda no existe.")

        if comanda.estado == Comanda.Estado.COBRADA:
            raise ValidationError("Esta comanda ya fue cobrada.")

        # Usar el primer método de pago disponible (o crear uno genérico)
        metodo_perdida = MetodoPago.objects.filter(codigo='PERDIDA', activo=True).first()
        if not metodo_perdida:
            # Si no existe el método PERDIDA, usar el primer método disponible
            metodo_perdida = MetodoPago.objects.filter(activo=True).first()
            if not metodo_perdida:
                raise ValidationError("No hay métodos de pago disponibles.")

        pago = Pago.objects.create(
            caja_turno=turno,
            comanda=comanda,
            metodo_pago=metodo_perdida,
            monto=comanda.total,
            vuelto=Decimal('0'),
            estado=Pago.Estado.PERDIDA,
            observacion=observacion or 'Cliente no pagó',
        )

        # Marcar como COBRADA aunque sea pérdida (para que no quede abierta)
        comanda.estado = Comanda.Estado.COBRADA
        comanda.fecha_cierre = timezone.now()
        comanda.save(update_fields=['estado', 'fecha_cierre'])

        _liberar_mesas_comanda(comanda)

        return pago
