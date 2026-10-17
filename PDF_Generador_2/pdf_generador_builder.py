"""
pdf_generador_builder.py
Constructor de elementos visuales (Flowables) para el documento ReportLab.
Garantiza un diseño limpio, profesional y 100% libre de tarjetas u opacidades.
"""
from typing import Dict, Any, List
from reportlab.platypus import Paragraph, Spacer, Table, KeepTogether, HRFlowable
from reportlab.lib import colors

from .pdf_generador_config import (
    USABLE_WIDTH,
    COLOR_PRIMARIO,
    COLOR_BORDE_TABLA,
    COLOR_LINEA_DIVISORIA
)
from .pdf_generador_estilos import PDFGeneradorEstilos


class PDFGeneradorBuilder:
    """Construye los bloques de contenido de la cotización."""

    def __init__(self, datos: Dict[str, Any]):
        self.datos = datos
        self.estilos = PDFGeneradorEstilos.obtener_estilos_texto()

    def construir_flujo(self) -> List[Any]:
        """Ensambla el flujo completo de elementos."""
        story = []

        # 1. Encabezado (Respeta logo izquierdo y ubica datos a la derecha)
        story.append(self._construir_encabezado())
        story.append(Spacer(1, 10))

        # 2. Metadatos del Cliente (Texto directo sin cards)
        story.append(self._construir_datos_cliente())
        story.append(Spacer(1, 8))

        # 3. Línea divisoria sutil
        story.append(HRFlowable(
            width="100%",
            thickness=0.75,
            color=COLOR_LINEA_DIVISORIA,
            spaceBefore=0,
            spaceAfter=6
        ))

        # 4. Tabla de Productos
        story.append(self._construir_tabla_productos())
        story.append(Spacer(1, 8))

        # 5. Sección final (Totales, Responsable, Condiciones y Firmas)
        story.append(self._construir_seccion_cierre())

        return story

    def _construir_encabezado(self) -> Table:
        """
        Crea el encabezado superior:
        - Columna izquierda vacía para dejar visible el logotipo I.E.E.I. pre-impreso.
        - Columna derecha con Título, Código de Cotización y Fecha.
        """
        cotizacion = self.datos.get('cotizacion', {})
        numero_cot = cotizacion.get('solicitud_numero', 'S/N')
        fecha = cotizacion.get('fecha', '')

        col_izq = []  # Libre para respetar el logo en FondoCotizacion.png

        col_der = [
            Paragraph("COTIZACIÓN DE VENTAS", self.estilos['titulo_documento']),
            Paragraph(f"COT-{numero_cot}", self.estilos['codigo_documento']),
            Paragraph(f"<b>Fecha:</b> {fecha}", self.estilos['fecha_header'])
        ]

        # Ancho: 50% izquierda (zona logo), 50% derecha
        ancho_izq = USABLE_WIDTH * 0.45
        ancho_der = USABLE_WIDTH * 0.55

        tabla_header = Table([[col_izq, col_der]], colWidths=[ancho_izq, ancho_der])
        tabla_header.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())
        return tabla_header

    def _construir_datos_cliente(self) -> Table:
        """
        Muestra los datos del cliente y condiciones comerciales en 2 columnas,
        flotando directamente sobre la imagen, sin cajas ni fondos opacos.
        """
        cliente = self.datos.get('cliente', {})
        cotizacion = self.datos.get('cotizacion', {})

        nombre_cliente = cliente.get('nombre', 'Cliente no especificado')
        nit_cliente = cliente.get('nit') or 'S/A'
        tel_cliente = cliente.get('telefono') or 'S/N'

        fecha = cotizacion.get('fecha', '')
        validez = cotizacion.get('validez', '1 Día')
        moneda = cotizacion.get('moneda', 'Bolivianos (Bs)')

        # Formato de 2 columnas limpias
        fila_1 = [
            Paragraph(f"<b>Cliente:</b> {nombre_cliente}", self.estilos['cliente_valor']),
            Paragraph(f"<b>Fecha:</b> {fecha}", self.estilos['cliente_valor'])
        ]
        fila_2 = [
            Paragraph(f"<b>NIT / CI:</b> {nit_cliente}", self.estilos['cliente_valor']),
            Paragraph(f"<b>Validez:</b> {validez}", self.estilos['cliente_valor'])
        ]
        fila_3 = [
            Paragraph(f"<b>Teléfono:</b> {tel_cliente}", self.estilos['cliente_valor']),
            Paragraph(f"<b>Moneda:</b> {moneda}", self.estilos['cliente_valor'])
        ]

        ancho_col = USABLE_WIDTH * 0.50
        tabla_cliente = Table([fila_1, fila_2, fila_3], colWidths=[ancho_col, ancho_col])
        tabla_cliente.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())
        return tabla_cliente

    def _construir_tabla_productos(self) -> Table:
        """
        Construye la grilla de productos con transparencia total.
        """
        productos = self.datos.get('productos', [])

        # Encabezados de tabla
        encabezados = [
            Paragraph("#", self.estilos['th_texto']),
            Paragraph("Código", self.estilos['th_texto']),
            Paragraph("Descripción", self.estilos['th_texto']),
            Paragraph("Marca", self.estilos['th_texto']),
            Paragraph("Cant.", self.estilos['th_texto']),
            Paragraph("U/M", self.estilos['th_texto']),
            Paragraph("P. Unitario", self.estilos['th_texto']),
            Paragraph("Total", self.estilos['th_texto'])
        ]

        filas = [encabezados]

        for idx, prod in enumerate(productos, start=1):
            precio_u = prod.get('precio_unitario', 0.0) or 0.0
            subtot = prod.get('subtotal', 0.0) or 0.0

            fila = [
                Paragraph(str(idx), self.estilos['td_centro']),
                Paragraph(str(prod.get('codigo', 'S/N')), self.estilos['td_centro']),
                Paragraph(str(prod.get('descripcion', '')), self.estilos['td_texto']),
                Paragraph(str(prod.get('marca', 'S/M')), self.estilos['td_centro']),
                Paragraph(str(prod.get('cantidad', 0)), self.estilos['td_centro']),
                Paragraph(str(prod.get('um', 'UN')), self.estilos['td_centro']),
                Paragraph(f"Bs {precio_u:,.2f}", self.estilos['td_monto']),
                Paragraph(f"Bs {subtot:,.2f}", self.estilos['td_monto'])
            ]
            filas.append(fila)

        # Distribución de anchos de columna (Suma = USABLE_WIDTH)
        # Total aprox: 25 + 50 + 215 + 65 + 35 + 35 + 75 + 75 = 575
        factor = USABLE_WIDTH / 575.0
        anchos = [
            25 * factor,   # #
            50 * factor,   # Código
            215 * factor,  # Descripción
            65 * factor,   # Marca
            35 * factor,   # Cantidad
            35 * factor,   # U/M
            75 * factor,   # Precio Unitario
            75 * factor    # Total
        ]

        tabla = Table(filas, colWidths=anchos, repeatRows=1)
        tabla.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_productos())
        return tabla

    def _construir_seccion_cierre(self) -> KeepTogether:
        """
        Mantiene juntos los totales, condiciones comerciales y firmas,
        evitando cortes antiestéticos de página.
        """
        elementos = []

        # 1. Monto literal
        total_letras = self.datos.get('total_letras', '')
        if total_letras:
            elementos.append(Paragraph(f"<b>SON:</b> {total_letras}", self.estilos['literal_monto']))

        # 2. Bloque Responsable (Izquierda) + Totales (Derecha)
        subtotal = self.datos.get('subtotal', 0.0) or 0.0
        descuento_monto = self.datos.get('monto_descuento', 0.0) or 0.0
        total = self.datos.get('total', 0.0) or 0.0

        usuario = self.datos.get('usuario', {})
        nombre_resp = usuario.get('nombre') or self.datos.get('usuario_sesion', 'Santiago Mendoza Soria')
        tel_resp = usuario.get('telefono') or '71234567'
        email_resp = usuario.get('email') or 'ieeimendoza@gmail.com'

        col_responsable = [
            Paragraph("<b>RESPONSABLE Y CONSULTA</b>", self.estilos['seccion_titulo']),
            Paragraph(f"<b>Nombre:</b> {nombre_resp}", self.estilos['condicion_item']),
            Paragraph(f"<b>Celular:</b> {tel_resp}", self.estilos['condicion_item']),
            Paragraph(f"<b>E-mail:</b> {email_resp}", self.estilos['condicion_item'])
        ]

        filas_totales = [
            [Paragraph("Subtotal:", self.estilos['total_label']), Paragraph(f"Bs {subtotal:,.2f}", self.estilos['total_valor'])],
        ]
        if descuento_monto > 0:
            filas_totales.append([
                Paragraph("Descuento:", self.estilos['total_label']),
                Paragraph(f"- Bs {descuento_monto:,.2f}", self.estilos['total_valor'])
            ])
        filas_totales.append([
            Paragraph("TOTAL:", self.estilos['gran_total_label']),
            Paragraph(f"Bs {total:,.2f}", self.estilos['gran_total_valor'])
        ])

        tabla_totales = Table(filas_totales, colWidths=[USABLE_WIDTH * 0.22, USABLE_WIDTH * 0.23])
        tabla_totales.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())

        tabla_distribucion = Table([[col_responsable, tabla_totales]], colWidths=[USABLE_WIDTH * 0.55, USABLE_WIDTH * 0.45])
        tabla_distribucion.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())
        elementos.append(tabla_distribucion)
        elementos.append(Spacer(1, 8))

        # 3. Condiciones
        elementos.append(Paragraph("<b>CONDICIONES</b>", self.estilos['seccion_titulo']))
        condiciones_tabla = Table([
            [
                Paragraph("<b>TIEMPO DE VALIDEZ:</b> 15 Días", self.estilos['condicion_item']),
                Paragraph("<b>PLAZO DE ENTREGA:</b> De acuerdo a existencia / 48 horas", self.estilos['condicion_item'])
            ]
        ], colWidths=[USABLE_WIDTH * 0.50, USABLE_WIDTH * 0.50])
        condiciones_tabla.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())
        elementos.append(condiciones_tabla)
        elementos.append(Spacer(1, 20))

        # 4. Sección de Firmas
        firmas_data = [
            [
                Paragraph("___________________________________", self.estilos['firma_linea']),
                Paragraph("___________________________________", self.estilos['firma_linea'])
            ],
            [
                Paragraph("FIRMA RESPONSABLE", self.estilos['firma_label']),
                Paragraph("FIRMA CLIENTE", self.estilos['firma_label'])
            ]
        ]
        tabla_firmas = Table(firmas_data, colWidths=[USABLE_WIDTH * 0.50, USABLE_WIDTH * 0.50])
        tabla_firmas.setStyle(PDFGeneradorEstilos.obtener_estilo_tabla_cliente())
        elementos.append(tabla_firmas)

        return KeepTogether(elementos)
