"""
pdf_generador_canvas.py
Canvas personalizado de ReportLab.
Dibuja FondoCotizacion.png como fondo directo bajo el contenido,
garantizando visibilidad total de la marca de agua, logo pre-impreso y pie de página.
"""
import os
from reportlab.pdfgen import canvas
from .pdf_generador_config import (
    PAGE_WIDTH,
    PAGE_HEIGHT,
    FONDO_UNICA_PAGINA,
    FONDO_PAGINA_1,
    FONDO_PAGINA_MEDIA,
    FONDO_PAGINA_FINAL
)


class PDFGeneradorCanvas(canvas.Canvas):
    """
    Canvas de doble pasada para ReportLab:
    1. Registra todas las páginas generadas para conocer el número total.
    2. Aplica FondoCotizacion.png en el fondo exacto de cada página.
    3. Permite que el texto y las tablas se impriman directamente sobre el fondo.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        # Guardar el estado de la página para la segunda pasada
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_paginas = len(self._saved_page_states)

        for page_idx, state in enumerate(self._saved_page_states):
            self.__dict__.update(state)
            page_num = page_idx + 1

            # Determinar fondo según número de páginas
            fondo_path = self._seleccionar_fondo(page_num, num_paginas)

            # Dibujar la imagen de fondo cubriendo toda la hoja
            if os.path.exists(fondo_path):
                self.saveState()
                self.drawImage(
                    fondo_path,
                    0,
                    0,
                    width=PAGE_WIDTH,
                    height=PAGE_HEIGHT,
                    preserveAspectRatio=False,
                    mask='auto'
                )
                self.restoreState()

            canvas.Canvas.showPage(self)

        canvas.Canvas.save(self)

    def _seleccionar_fondo(self, pagina_actual: int, total_paginas: int) -> str:
        """
        Selecciona la imagen de fondo adecuada según la hoja.
        Para 1 sola página: FondoCotizacion.png
        Para 2+ páginas: FondoCotizacion2, Media y Final.
        """
        if total_paginas == 1:
            return FONDO_UNICA_PAGINA

        # Cotizaciones de 2 o más páginas
        if pagina_actual == 1:
            return FONDO_PAGINA_1 if os.path.exists(FONDO_PAGINA_1) else FONDO_UNICA_PAGINA
        elif pagina_actual == total_paginas:
            return FONDO_PAGINA_FINAL if os.path.exists(FONDO_PAGINA_FINAL) else FONDO_UNICA_PAGINA
        else:
            return FONDO_PAGINA_MEDIA if os.path.exists(FONDO_PAGINA_MEDIA) else FONDO_UNICA_PAGINA
