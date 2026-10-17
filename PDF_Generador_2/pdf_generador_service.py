"""
pdf_generador_service.py
Servicio principal para la generación de PDFs con ReportLab.
Punto de entrada limpio que genera los bytes finales del PDF.
"""
import os
import io
from typing import Dict, Any
from reportlab.platypus import SimpleDocTemplate

from .pdf_generador_config import (
    PAGE_WIDTH,
    PAGE_HEIGHT,
    MARGIN_LEFT,
    MARGIN_RIGHT,
    MARGIN_TOP,
    MARGIN_BOTTOM,
    FONDO_UNICA_PAGINA
)
from .pdf_generador_canvas import PDFGeneradorCanvas
from .pdf_generador_builder import PDFGeneradorBuilder


class PDFGeneradorService:
    """Servicio orquestador para la creación de cotizaciones en PDF."""

    @classmethod
    def generar_pdf_bytes(cls, datos: Dict[str, Any]) -> bytes:
        """
        Genera el PDF en memoria y devuelve los bytes resultantes.
        """
        buffer = io.BytesIO()

        # Configurar el documento Platypus
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM
        )

        def _dibujar_fondo(canvas_obj, doc_obj):
            """Dibuja FondoCotizacion.png en la capa base antes de los flowables."""
            if os.path.exists(FONDO_UNICA_PAGINA):
                canvas_obj.saveState()
                canvas_obj.drawImage(
                    FONDO_UNICA_PAGINA,
                    0,
                    0,
                    width=PAGE_WIDTH,
                    height=PAGE_HEIGHT,
                    preserveAspectRatio=False,
                    mask='auto'
                )
                canvas_obj.restoreState()

        # Construir los flowables
        builder = PDFGeneradorBuilder(datos)
        story = builder.construir_flujo()

        # Compilar dibujando el fondo antes del texto
        doc.build(story, onFirstPage=_dibujar_fondo, onLaterPages=_dibujar_fondo)

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


def generar_cotizacion_pdf_v2(datos: Dict[str, Any]) -> bytes:
    """Función de acceso directo para generar cotización en PDF v2."""
    return PDFGeneradorService.generar_pdf_bytes(datos)
