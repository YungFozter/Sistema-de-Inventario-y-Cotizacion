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
    FONDO_UNICA_PAGINA,
    FONDO_PAGINA_1,
    FONDO_PAGINA_MEDIA,
    FONDO_PAGINA_FINAL
)
from .pdf_generador_canvas import PDFGeneradorCanvas
from .pdf_generador_builder import PDFGeneradorBuilder


class PDFGeneradorService:
    """Servicio orquestador para la creación de cotizaciones en PDF."""

    @classmethod
    def generar_pdf_bytes(cls, datos: Dict[str, Any]) -> bytes:
        """
        Genera el PDF en memoria y devuelve los bytes resultantes.
        Calcula dinámicamente el número total de páginas y asigna el fondo exacto:
        - 1 página: FondoCotizacion.png
        - 2 páginas: FondoCotizacion2.png (pág 1) y FondoCotizacionHojaFinal.png (pág 2)
        - 3+ páginas: FondoCotizacion2.png (pág 1), FondoCotizacionHojaMedia.png (intermedias), FondoCotizacionHojaFinal.png (final)
        """
        # Paso 1: Medición preliminar para calcular el total exacto de páginas
        dummy_buffer = io.BytesIO()
        dummy_doc = SimpleDocTemplate(
            dummy_buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM
        )
        dummy_story = PDFGeneradorBuilder(datos).construir_flujo()
        dummy_doc.build(dummy_story)
        total_paginas = dummy_doc.page
        dummy_buffer.close()

        # Paso 2: Función selectora de fondo según la regla de negocio
        def _obtener_ruta_fondo(num_pagina: int) -> str:
            if total_paginas == 1:
                return FONDO_UNICA_PAGINA

            # Para documentos de 2 o más páginas
            if num_pagina == 1:
                return FONDO_PAGINA_1 if os.path.exists(FONDO_PAGINA_1) else FONDO_UNICA_PAGINA
            elif num_pagina == total_paginas:
                return FONDO_PAGINA_FINAL if os.path.exists(FONDO_PAGINA_FINAL) else FONDO_UNICA_PAGINA
            else:
                return FONDO_PAGINA_MEDIA if os.path.exists(FONDO_PAGINA_MEDIA) else FONDO_UNICA_PAGINA

        # Paso 3: Renderizado final con el fondo adecuado estampado en cada hoja
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM
        )

        def _dibujar_fondo_dinamico(canvas_obj, doc_obj):
            pagina_actual = canvas_obj._pageNumber
            ruta_fondo = _obtener_ruta_fondo(pagina_actual)

            if os.path.exists(ruta_fondo):
                canvas_obj.saveState()
                canvas_obj.drawImage(
                    ruta_fondo,
                    0,
                    0,
                    width=PAGE_WIDTH,
                    height=PAGE_HEIGHT,
                    preserveAspectRatio=False,
                    mask='auto'
                )
                canvas_obj.restoreState()

        final_story = PDFGeneradorBuilder(datos).construir_flujo()
        doc.build(final_story, onFirstPage=_dibujar_fondo_dinamico, onLaterPages=_dibujar_fondo_dinamico)

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


def generar_cotizacion_pdf_v2(datos: Dict[str, Any]) -> bytes:
    """Función de acceso directo para generar cotización en PDF v2."""
    return PDFGeneradorService.generar_pdf_bytes(datos)
