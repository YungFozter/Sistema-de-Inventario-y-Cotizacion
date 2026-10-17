"""
pdf_generador_config.py
Configuración de dimensiones, márgenes y rutas para el generador PDF ReportLab.
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm, mm, inch
from reportlab.lib import colors

# Tamaño de página estándar (Letter: 612 x 792 pt)
PAGE_WIDTH, PAGE_HEIGHT = letter

# Márgenes del documento
MARGIN_LEFT = 14 * mm
MARGIN_RIGHT = 14 * mm
MARGIN_TOP = 14 * mm
MARGIN_BOTTOM = 18 * mm

# Ancho útil imprimible
USABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

# Rutas de imágenes base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')

FONDO_UNICA_PAGINA = os.path.join(IMAGES_DIR, 'FondoCotizacion.png')
FONDO_PAGINA_1 = os.path.join(IMAGES_DIR, 'FondoCotizacion2.png')
FONDO_PAGINA_MEDIA = os.path.join(IMAGES_DIR, 'FondoCotizacionHojaMedia.png')
FONDO_PAGINA_FINAL = os.path.join(IMAGES_DIR, 'FondoCotizacionHojaFinal.png')

# Paleta de colores profesionales
COLOR_PRIMARIO = colors.HexColor('#1e3a8a')     # Azul oscuro elegante
COLOR_SECUNDARIO = colors.HexColor('#0f172a')   # Casi negro / texto principal
COLOR_MUTED = colors.HexColor('#475569')        # Gris neutro oscuro legible
COLOR_BORDE_TABLA = colors.HexColor('#94a3b8')  # Borde sutil
COLOR_LINEA_DIVISORIA = colors.HexColor('#cbd5e1')
COLOR_ACCENTO = colors.HexColor('#0284c7')
