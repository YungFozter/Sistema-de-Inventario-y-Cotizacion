"""
pdf_generador_estilos.py
Definición de estilos tipográficos y tablas para ReportLab.
Garantiza fondos 100% transparentes, sin cards ni cajas opacas.
"""
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import TableStyle
from reportlab.lib import colors

from .pdf_generador_config import (
    COLOR_PRIMARIO,
    COLOR_SECUNDARIO,
    COLOR_MUTED,
    COLOR_BORDE_TABLA,
    COLOR_LINEA_DIVISORIA
)


class PDFGeneradorEstilos:
    """Proveedor centralizado de estilos de texto y tablas."""

    @classmethod
    def obtener_estilos_texto(cls):
        base_sheet = getSampleStyleSheet()

        return {
            # Encabezado Derecho
            'titulo_documento': ParagraphStyle(
                'TituloDoc',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=14,
                leading=16,
                textColor=COLOR_PRIMARIO,
                alignment=TA_RIGHT,
                spaceAfter=2
            ),
            'codigo_documento': ParagraphStyle(
                'CodigoDoc',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=10,
                leading=12,
                textColor=COLOR_MUTED,
                alignment=TA_RIGHT,
                spaceAfter=4
            ),
            'fecha_header': ParagraphStyle(
                'FechaHeader',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_MUTED,
                alignment=TA_RIGHT
            ),

            # Sección Datos Cliente (Sin caja, texto directo)
            'cliente_label': ParagraphStyle(
                'ClienteLabel',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_SECUNDARIO
            ),
            'cliente_valor': ParagraphStyle(
                'ClienteValor',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_SECUNDARIO
            ),

            # Tabla de Productos
            'th_texto': ParagraphStyle(
                'ThTexto',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=10,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_CENTER
            ),
            'td_texto': ParagraphStyle(
                'TdTexto',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=9.5,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_LEFT
            ),
            'td_centro': ParagraphStyle(
                'TdCentro',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=9.5,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_CENTER
            ),
            'td_monto': ParagraphStyle(
                'TdMonto',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=9.5,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_RIGHT
            ),

            # Totales y Monto Literal
            'literal_monto': ParagraphStyle(
                'LiteralMonto',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Oblique',
                fontSize=8,
                leading=10,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_LEFT,
                spaceBefore=4,
                spaceAfter=6
            ),
            'total_label': ParagraphStyle(
                'TotalLabel',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_RIGHT
            ),
            'total_valor': ParagraphStyle(
                'TotalValor',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_RIGHT
            ),
            'gran_total_label': ParagraphStyle(
                'GranTotalLabel',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=10,
                leading=13,
                textColor=COLOR_PRIMARIO,
                alignment=TA_RIGHT
            ),
            'gran_total_valor': ParagraphStyle(
                'GranTotalValor',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=10,
                leading=13,
                textColor=COLOR_PRIMARIO,
                alignment=TA_RIGHT
            ),

            # Condiciones y Notas
            'seccion_titulo': ParagraphStyle(
                'SeccionTitulo',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                textColor=COLOR_PRIMARIO,
                spaceBefore=6,
                spaceAfter=3
            ),
            'condicion_item': ParagraphStyle(
                'CondicionItem',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=10,
                textColor=COLOR_SECUNDARIO
            ),

            # Firmas
            'firma_linea': ParagraphStyle(
                'FirmaLinea',
                parent=base_sheet['Normal'],
                fontName='Helvetica',
                fontSize=8,
                leading=10,
                textColor=COLOR_MUTED,
                alignment=TA_CENTER
            ),
            'firma_label': ParagraphStyle(
                'FirmaLabel',
                parent=base_sheet['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=10,
                textColor=COLOR_SECUNDARIO,
                alignment=TA_CENTER,
                spaceBefore=2
            )
        }

    @classmethod
    def obtener_estilo_tabla_productos(cls):
        """
        Estilo de tabla 100% transparente:
        - Sin color de fondo en th ni td (cero cajas).
        - Líneas divisorias horizontales limpias y sutiles.
        """
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.transparent),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            # Línea superior e inferior del encabezado
            ('LINEABOVE', (0, 0), (-1, 0), 1.0, COLOR_PRIMARIO),
            ('LINEBELOW', (0, 0), (-1, 0), 1.0, COLOR_PRIMARIO),
            # Líneas sutiles entre filas
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, COLOR_LINEA_DIVISORIA),
        ])

    @classmethod
    def obtener_estilo_tabla_cliente(cls):
        """Metadatos del cliente con transparencia total y sin marcos pesados."""
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.transparent),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ])
