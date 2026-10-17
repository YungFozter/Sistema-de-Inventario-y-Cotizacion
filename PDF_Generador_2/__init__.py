"""
PDF_Generador_2
Módulo independiente de generación de PDFs de cotización mediante ReportLab nativo.
Garantiza cero dependencias externas, transparencia total y diseño limpio sin tarjetas opacas.
"""
from .pdf_generador_service import PDFGeneradorService, generar_cotizacion_pdf_v2
from .pdf_generador_config import PAGE_WIDTH, PAGE_HEIGHT, FONDO_UNICA_PAGINA

__all__ = [
    'PDFGeneradorService',
    'generar_cotizacion_pdf_v2',
    'PAGE_WIDTH',
    'PAGE_HEIGHT',
    'FONDO_UNICA_PAGINA'
]
