from flask import Flask, flash, render_template, request, redirect, session, url_for, make_response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pdfkit
from num2words import num2words
from datetime import datetime
import os
import time
import base64
import json
import sqlite3
import random
import string
from db_wrapper import get_db_connection
from sqlite3 import connect  # Esta es la importación que faltaba
from markupsafe import Markup
from threading import Lock
from contextlib import contextmanager
from models import (
    crear_tablas, registrar_log, migrar_clientes_existentes, migrar_productos_categorias,
    migrar_columnas_nuevas_clientes,
    guardar_importacion_pdf, obtener_importaciones_pdf, obtener_importacion_por_id, registrar_productos_seleccionados,
    eliminar_importacion_pdf
)
from utils.pdf_extractor import PDFProductExtractor
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
import logging
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.ERROR)

@app.template_filter('date')
def format_date(value, format='%d/%m/%Y'):
    if value is None:
        return ""

    # Si ya es un objeto datetime
    if isinstance(value, datetime):
        return value.strftime(format)

    # Si es string, intenta parsear
    if isinstance(value, str):
        formats_to_try = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y',
            '%m/%d/%Y'
        ]

        for fmt in formats_to_try:
            try:
                return datetime.strptime(value, fmt).strftime(format)
            except ValueError:
                continue

    # Si no se pudo parsear, devolver el valor original
    return str(value)

def aplicar_fondos_por_pagina(pdf_bytes):
    """
    Aplica diferentes fondos según el número de páginas con márgenes dinámicos:
    - 1 página: FondoCotizacion.png
    - +2 páginas: FondoCotizacionHojaMedia.png para páginas intermedias, FondoCotizacionHojaFinal.png para la última
    - A partir de la 2da página: aplica margen superior adicional para mejor estética
    """
    try:
        app.logger.info("=== INICIANDO APLICACIÓN DE FONDOS ===")
        
        # Leer el PDF original
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        pdf_writer = PdfWriter()
        num_pages = len(pdf_reader.pages)
        
        app.logger.info(f"PDF original tiene {num_pages} páginas")
        
        # Cargar las imágenes de fondo según nueva especificación
        fondo_unica_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
        fondo_intermedia_path = os.path.join(app.static_folder, 'images', 'FondoCotizacionHojaMedia.png')
        fondo_final_path = os.path.join(app.static_folder, 'images', 'FondoCotizacionHojaFinal.png')
        fondo2_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion2.png')  # Para páginas de 2 hojas
        
        app.logger.info(f"Buscando FondoCotizacion.png en: {fondo_unica_path}")
        app.logger.info(f"Buscando FondoCotizacionHojaMedia.png en: {fondo_intermedia_path}")
        app.logger.info(f"Buscando FondoCotizacionHojaFinal.png en: {fondo_final_path}")
        app.logger.info(f"Buscando FondoCotizacion2.png en: {fondo2_path}")
        
        # Verificar que existan las imágenes principales
        if not os.path.exists(fondo_unica_path):
            app.logger.error(f"ERROR: No se encontró FondoCotizacion.png en: {fondo_unica_path}")
            return pdf_bytes
        else:
            app.logger.info(f"✓ FondoCotizacion.png encontrado, tamaño: {os.path.getsize(fondo_unica_path)} bytes")
        
        # Verificar imágenes para múltiples páginas
        if num_pages > 1:
            # Verificar FondoCotizacion2.png para documentos de 2 páginas
            if not os.path.exists(fondo2_path):
                app.logger.warning(f"No se encontró FondoCotizacion2.png en: {fondo2_path}")
                app.logger.info("Usando FondoCotizacion.png para primera página de documentos de 2 hojas")
                fondo2_path = fondo_unica_path
            else:
                app.logger.info(f"✓ FondoCotizacion2.png encontrado, tamaño: {os.path.getsize(fondo2_path)} bytes")
            
            if not os.path.exists(fondo_intermedia_path):
                app.logger.warning(f"No se encontró FondoCotizacionHojaMedia.png en: {fondo_intermedia_path}")
                app.logger.info("Usando FondoCotizacion.png para páginas intermedias")
                fondo_intermedia_path = fondo_unica_path
            else:
                app.logger.info(f"✓ FondoCotizacionHojaMedia.png encontrado, tamaño: {os.path.getsize(fondo_intermedia_path)} bytes")
            
            if not os.path.exists(fondo_final_path):
                app.logger.warning(f"No se encontró FondoCotizacionHojaFinal.png en: {fondo_final_path}")
                app.logger.info("Usando FondoCotizacion.png para página final")
                fondo_final_path = fondo_unica_path
            else:
                app.logger.info(f"✓ FondoCotizacionHojaFinal.png encontrado, tamaño: {os.path.getsize(fondo_final_path)} bytes")
        
        # Procesar cada página
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            
            # Determinar qué fondo usar según nueva lógica
            if num_pages == 1:
                # Una sola página: usar FondoCotizacion.png
                fondo_path = fondo_unica_path
                fondo_nombre = "FondoCotizacion.png (página única)"
                margen_superior_extra = 0
            elif num_pages == 2:
                # Caso especial: exactamente 2 páginas
                if page_num == 0:
                    # Primera página de 2: usar FondoCotizacion2.png
                    fondo_path = fondo2_path
                    fondo_nombre = "FondoCotizacion2.png (primera de 2 páginas)"
                    margen_superior_extra = 0
                else:
                    # Segunda página de 2: usar FondoCotizacionHojaFinal.png
                    fondo_path = fondo_final_path
                    fondo_nombre = "FondoCotizacionHojaFinal.png (segunda de 2 páginas)"
                    margen_superior_extra = 40  # Margen extra para página 2
            else:
                # Múltiples páginas (3 o más)
                if page_num == 0:
                    # Primera página de 3+: usar FondoCotizacion2.png
                    fondo_path = fondo2_path
                    fondo_nombre = "FondoCotizacion2.png (primera de múltiples páginas)"
                    margen_superior_extra = 0
                elif page_num == num_pages - 1:
                    # Última página: usar FondoCotizacionHojaFinal.png
                    fondo_path = fondo_final_path
                    fondo_nombre = "FondoCotizacionHojaFinal.png (página final)"
                    margen_superior_extra = 40  # Margen extra para páginas 2+
                else:
                    # Páginas intermedias (2 a N-1): usar FondoCotizacionHojaMedia.png
                    fondo_path = fondo_intermedia_path
                    fondo_nombre = "FondoCotizacionHojaMedia.png (página intermedia)"
                    margen_superior_extra = 40  # Margen extra para páginas 2+
            
            app.logger.info(f"Procesando página {page_num + 1} con {fondo_nombre}")
            
            # Obtener dimensiones de la página
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            
            app.logger.info(f"Dimensiones página: {page_width}x{page_height}")
            
            # Crear un PDF temporal con el fondo usando las mismas dimensiones que la página
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))
            
            # Dibujar la imagen de fondo
            if os.path.exists(fondo_path):
                try:
                    app.logger.info(f"Aplicando fondo: {fondo_path}")
                    
                    # Abrir la imagen y obtener sus dimensiones
                    with Image.open(fondo_path) as img:
                        img_width, img_height = img.size
                    
                    app.logger.info(f"Dimensiones imagen: {img_width}x{img_height}")
                    
                    # Dibujar la imagen ocupando toda la página
                    # Usar drawImage simple que es más confiable
                    can.drawImage(fondo_path, 0, 0, 
                                width=page_width, height=page_height)
                    
                    app.logger.info(f"✓ Fondo aplicado exitosamente en página {page_num + 1}")
                    
                except Exception as e:
                    app.logger.error(f"ERROR al dibujar fondo en página {page_num + 1}: {e}")
                    import traceback
                    app.logger.error(f"Traceback: {traceback.format_exc()}")
            else:
                app.logger.error(f"ERROR: Archivo de fondo no existe: {fondo_path}")
            
            can.save()
            
            # Crear página de fondo
            packet.seek(0)
            background_pdf = PdfReader(packet)
            
            if len(background_pdf.pages) == 0:
                app.logger.error("ERROR: No se pudo crear página de fondo")
                pdf_writer.add_page(page)
                continue
                
            background_page = background_pdf.pages[0]
            
            # Aplicar transformación de margen superior a partir de la página 2
            if margen_superior_extra > 0:
                try:
                    # Crear una transformación para mover el contenido hacia abajo
                    from PyPDF2.generic import Transformation
                    transformation = Transformation().translate(tx=0, ty=-margen_superior_extra)
                    page.add_transformation(transformation)
                    app.logger.info(f"Aplicado margen superior extra de {margen_superior_extra} en página {page_num + 1}")
                except Exception as e:
                    app.logger.warning(f"No se pudo aplicar margen extra en página {page_num + 1}: {e}")
            
            # Combinar fondo con contenido (el 'background_page' va sobre 'page' para que no lo tape el lienzo blanco)
            try:
                page.merge_page(background_page)
                pdf_writer.add_page(page)
                app.logger.info(f"✓ Página {page_num + 1} procesada y agregada exitosamente")
            except Exception as e:
                try:
                    background_page.merge_page(page)
                    pdf_writer.add_page(background_page)
                except Exception as e2:
                    app.logger.error(f"ERROR al combinar página {page_num + 1}: {e2}")
                    pdf_writer.add_page(page)
        
        app.logger.info("Generando PDF final...")
        
        # Generar el PDF final
        output_stream = io.BytesIO()
        pdf_writer.write(output_stream)
        final_pdf = output_stream.getvalue()
        
        app.logger.info(f"✓ PDF final generado, tamaño: {len(final_pdf)} bytes")
        return final_pdf
        
    except Exception as e:
        app.logger.error(f"ERROR CRÍTICO aplicando fondos por página: {e}")
        import traceback
        app.logger.error(f"Traceback completo: {traceback.format_exc()}")
        # En caso de error, devolver el PDF original
        return pdf_bytes

def generar_pdf_margenes_dinamicos(html, config, cotizacion_id):
    """
    Genera un PDF con márgenes dinámicos y fondos específicos por página
    para cotizaciones de múltiples páginas con mejor estética
    """
    try:
        # Generar PDF inicial para conocer el número de páginas
        options_test = {
            'enable-local-file-access': None,
            'encoding': 'UTF-8',
            'quiet': '',
            'margin-top': '10mm',
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
            'no-background': ''
        }
        
        pdf_test = pdfkit.from_string(html, False, configuration=config, options=options_test)
        test_reader = PdfReader(io.BytesIO(pdf_test))
        num_pages = len(test_reader.pages)
        
        if num_pages == 1:
            # Si resulta ser una sola página, usar el método simple
            return aplicar_fondos_por_pagina(pdf_test)
        
        # Para múltiples páginas, generar con márgenes optimizados
        # Primera página: margen normal
        # Páginas 2+: margen superior incrementado para respetar el diseño del fondo
        
        options_multipagina = {
            'enable-local-file-access': None,
            'encoding': 'UTF-8',
            'quiet': '',
            'margin-top': '15mm',      # Margen superior más amplio para páginas 2+
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
            'header-spacing': '5',      # Espacio adicional para el header en páginas 2+
            'no-background': ''
        }
        
        # Generar el PDF final con márgenes optimizados
        pdf_final = pdfkit.from_string(html, False, configuration=config, options=options_multipagina)
        
        # Aplicar fondos específicos por página
        return aplicar_fondos_por_pagina(pdf_final)
        
    except Exception as e:
        app.logger.error(f"Error generando PDF con márgenes dinámicos: {e}")
        # En caso de error, generar PDF estándar
        options_fallback = {
            'enable-local-file-access': None,
            'encoding': 'UTF-8',
            'quiet': '',
            'margin-top': '10mm',
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
            'no-background': ''
        }
        pdf_fallback = pdfkit.from_string(html, False, configuration=config, options=options_fallback)
        return aplicar_fondos_por_pagina(pdf_fallback)

