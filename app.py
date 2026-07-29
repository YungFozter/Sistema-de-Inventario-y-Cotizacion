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

app = Flask(__name__)
app.secret_key = 'tu-clave-secreta-aqui'  # Cambia esto en producción

# Configurar logging para ver los mensajes de depuración
import logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Database connection pool
db_lock = Lock()



# Configuración de variables

# Configuración de variables
pin_admin = "Enrique"  # Clave para sesiones de administrador

# Inicializar la base de datos y crear un usuario superadmin por defecto si es necesario
with app.app_context():
    crear_tablas()
    migrar_clientes_existentes()
    migrar_productos_categorias()
    migrar_columnas_nuevas_clientes()

# Añadir filtro 'date' para Jinja2
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
            
            # Combinar fondo con contenido
            try:
                background_page.merge_page(page)
                pdf_writer.add_page(background_page)
                app.logger.info(f"✓ Página {page_num + 1} procesada y agregada exitosamente")
            except Exception as e:
                app.logger.error(f"ERROR al combinar página {page_num + 1}: {e}")
                # Si hay error, agregar la página original sin fondo
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
        }
        pdf_fallback = pdfkit.from_string(html, False, configuration=config, options=options_fallback)
        return aplicar_fondos_por_pagina(pdf_fallback)

# Context Processor para pasar 'now' a todas las plantillas
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# --- Decorador para requerir autenticación ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Registrar intento de acceso no autorizado
            registrar_log(
                usuario_id=None,
                accion="intento_acceso_no_autorizado",
                detalle={
                    "ruta": request.path,
                    "ip": request.remote_addr
                }
            )
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


#Decorador para requerir el rol de superAdmin
def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_rol' not in session or session['user_rol'] != 'superadmin':
            flash('Se requieren permisos de superadministrador', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para requerir rol de administrador
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_rol' not in session or session['user_rol'] not in ['admin', 'superadmin']:
            flash('Acceso denegado: Se requieren privilegios de administrador', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def standard_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_rol' not in session or session['user_rol'] != 'standard':
            flash('Acceso restringido a usuarios Standard', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Eliminar esta llamada redundante
# crear_tablas()

@app.route('/admin/usuarios/<int:id>', methods=['GET'])
@admin_required
@login_required
def obtener_usuario(id):
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        cursor.execute("SELECT id, nombre, correo, telefono, rol FROM clientes WHERE id = ?", (id,))
        usuario = cursor.fetchone()
        conexion.close()

        if usuario:
            return jsonify({
                'id': usuario[0],
                'nombre': usuario[1],
                'correo': usuario[2],
                'telefono': usuario[3],
                'rol': usuario[4]
            })
        else:
            return jsonify({'error': 'Usuario no encontrado'}), 404

    except Exception as e:
        app.logger.error(f"Error al obtener usuario {id}: {str(e)}")
        return jsonify({'error': 'Error del servidor'}), 500


@app.route('/admin/historial-usuarios')
@superadmin_required
def historial_usuarios():
    try:
        # Conexión a la base de datos
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row  # Para obtener resultados como diccionarios
        cursor = conexion.cursor()

        # Consulta optimizada para obtener los logs con información del usuario
        cursor.execute('''
            SELECT 
                l.id,
                l.usuario_id,
                u.nombre as usuario_nombre,
                l.accion,
                l.detalle,
                l.fecha,
                u.correo as usuario_email,
                u.rol as usuario_rol
            FROM logs l
            JOIN clientes u ON l.usuario_id = u.id
            ORDER BY l.fecha DESC
            LIMIT 100
        ''')

        historial = cursor.fetchall()

        # Registrar la consulta en el propio sistema de auditoría
        cursor.execute('''
            INSERT INTO logs (usuario_id, accion, detalle)
            VALUES (?, ?, ?)
        ''', (
            session.get('user_id'),
            'consulta_historial',
            json.dumps({
                'tipo': 'historial_auditoria',
                'resultados': len(historial)
            })
        ))
        conexion.commit()

        return render_template('admin/historial_usuarios.html',
                               historial=historial,
                               ahora=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    except sqlite3.Error as e:
        # En caso de error, registrar el fallo
        error_msg = f"Error al consultar historial: {str(e)}"
        print(error_msg)

        # Intentar registrar el error en logs (si la conexión aún está disponible)
        try:
            cursor.execute('''
                INSERT INTO logs (usuario_id, accion, detalle)
                VALUES (?, ?, ?)
            ''', (
                session.get('user_id'),
                'error_consulta_historial',
                json.dumps({
                    'error': str(e),
                    'tipo': 'historial_auditoria'
                })
            ))
            conexion.commit()
        except:
            pass

        flash('Error al cargar el historial de auditoría', 'danger')
        return redirect(url_for('admin_panel'))

    finally:
        if 'conexion' in locals():
            conexion.close()


@app.route('/admin/usuarios', methods=['POST'])
@admin_required
@login_required
def crear_usuario():
    try:
        # Obtener datos (compatible con form-data y JSON)
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        nombre = data.get('nombre')
        correo = data.get('correo')
        telefono = data.get('telefono', '')
        rol = data.get('rol')
        contrasena = data.get('contrasena')

        # Validaciones básicas
        if not all([nombre, correo, rol, contrasena]):
            return jsonify({'error': 'Faltan campos requeridos'}), 400

        if rol not in ['admin', 'standard']:
            return jsonify({'error': 'Rol no válido'}), 400

        # Validar que solo superadmin pueda crear otros admins
        if rol == 'admin' and session.get('user_rol') != 'superadmin':
            return jsonify({'error': 'Solo superadmin puede crear usuarios admin'}), 403

        conexion = get_db_connection()
        cursor = conexion.cursor()

        # Verificar correo único
        cursor.execute("SELECT id FROM clientes WHERE correo = ?", (correo,))
        if cursor.fetchone():
            conexion.close()
            return jsonify({'error': 'El correo ya está registrado'}), 400

        # Crear hash de la contraseña
        contrasena_hash = generate_password_hash(contrasena)

        # Insertar nuevo usuario
        cursor.execute('''
            INSERT INTO clientes (nombre, correo, telefono, rol, contrasena, creador_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nombre, correo, telefono, rol, contrasena_hash, session['user_id']))

        # Registrar en el historial
        registrar_log(
            usuario_id=session['user_id'],
            accion="crear_usuario",
            detalle={
                "tipo": rol,
                "email": correo,
                "nombre": nombre
            }
        )

        conexion.commit()
        conexion.close()

        # Corrección: Separar el código de estado del objeto JSON
        return jsonify({
            'success': True,
            'message': 'Usuario creado exitosamente'
        }), 201


    except sqlite3.Error as e:
        app.logger.error(f"Error en base de datos al crear usuario: {str(e)}")
        if 'conexion' in locals():
            conexion.rollback()
            conexion.close()
        return jsonify({'error': 'Error en la base de datos'}), 500

    except Exception as e:
        app.logger.error(f"Error al crear usuario: {str(e)}")
        return jsonify({'error': 'Error del servidor'}), 500


@app.route('/admin/usuarios/<int:id>', methods=['PUT'])
@admin_required
@login_required
def actualizar_usuario(id):
    try:
        data = request.get_json() if request.is_json else request.form
        nombre = data.get('nombre')
        correo = data['correo']
        telefono = data.get('telefono', '')
        rol = data['rol']
        contrasena = data.get('contrasena', '')

        # Validaciones
        if not nombre or not correo or not rol:
            return jsonify({'error': 'Faltan campos requeridos'}), 400

        if rol not in ['admin', 'standard']:
            return jsonify({'error': 'Rol no válido'}), 400

        # Verificar si el usuario existe
        conexion = get_db_connection()
        cursor = conexion.cursor()
        cursor.execute("SELECT id FROM clientes WHERE id = ?", (id,))
        if not cursor.fetchone():
            conexion.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404

        # Verificar si el correo ya existe para otro usuario
        cursor.execute("SELECT id FROM clientes WHERE correo = ? AND id != ?", (correo, id))
        if cursor.fetchone():
            conexion.close()
            return jsonify({'error': 'El correo ya está registrado por otro usuario'}), 400

        # Actualizar usuario
        if contrasena:
            contrasena_hash = generate_password_hash(contrasena)
            cursor.execute('''
                UPDATE clientes SET 
                    nombre = ?,
                    correo = ?,
                    telefono = ?,
                    rol = ?,
                    contrasena = ?
                WHERE id = ?
            ''', (nombre, correo, telefono, rol, contrasena_hash, id))
        else:
            cursor.execute('''
                UPDATE clientes SET 
                    nombre = ?,
                    correo = ?,
                    telefono = ?,
                    rol = ?
                WHERE id = ?
            ''', (nombre, correo, telefono, rol, id))

        conexion.commit()
        conexion.close()

        return jsonify({'success': True}), 200

    except Exception as e:
        app.logger.error(f"Error al actualizar usuario {id}: {str(e)}")
        return jsonify({'error': 'Error del servidor'}), 500


@app.route('/admin/usuarios/<int:id>/rol', methods=['PUT'])
@superadmin_required
@login_required
def cambiar_rol_usuario(id):
    # Validar que no sea el usuario actual
    if id == session['user_id']:
        return jsonify({'error': 'No puedes cambiar tu propio rol'}), 400

    data = request.get_json() if request.is_json else request.form
    nuevo_rol = data.get('rol')

    if nuevo_rol not in ['admin', 'standard']:
        return jsonify({'error': 'Rol no válido'}), 400

    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        cursor.execute("UPDATE clientes SET rol = ? WHERE id = ?", (nuevo_rol, id))
        conexion.commit()

        registrar_log(
            usuario_id=session['user_id'],
            accion="cambio_rol_usuario",
            detalle={
                "usuario_afectado": id,
                "nuevo_rol": nuevo_rol
            }
        )

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error al cambiar rol: {str(e)}")
        return jsonify({'error': 'Error interno'}), 500
    finally:
        if 'conexion' in locals():
            conexion.close()

@app.route('/admin/usuarios/<int:id>/estado', methods=['PUT'])
@login_required
def cambiar_estado_usuario(id):
    # Verificar permisos
    if session.get('user_rol') not in ['admin', 'superadmin']:
        return jsonify({'error': 'No autorizado'}), 403

    # Validar que no sea el usuario actual
    if id == session['user_id']:
        return jsonify({'error': 'No puedes cambiar tu propio estado'}), 400

    # Resto de la lógica común
    data = request.json
    activo = data.get('activo')

    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        cursor.execute("UPDATE clientes SET activo = ? WHERE id = ?", (activo, id))
        conexion.commit()

        registrar_log(
            usuario_id=session['user_id'],
            accion="cambio_estado_usuario",
            detalle={
                "usuario_afectado_id": id,
                "nuevo_estado": activo
            }
        )

        return jsonify({'success': True}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conexion' in locals():
            conexion.close()


# --- Vista principal para usuarios Standard ---
@app.route('/standard/dashboard')
@standard_required
@login_required
def standard_dashboard():
    # Obtener parámetros de filtro
    estado = request.args.get('estado', '')
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    conexion = get_db_connection()
    cursor = conexion.cursor()

    query = '''
        SELECT 
            c.id, 
            c.fecha, 
            c.total,
            c.estado
        FROM cotizaciones c
        WHERE c.cliente_id = ?
    '''
    params = [session['user_id']]

    # Aplicar filtros
    if estado:
        query += " AND c.estado = ?"
        params.append(estado)

    if desde:
        query += " AND DATE(c.fecha) >= ?"
        params.append(desde)

    if hasta:
        query += " AND DATE(c.fecha) <= ?"
        params.append(hasta)

    query += " ORDER BY c.fecha DESC"

    cursor.execute(query, params)
    cotizaciones = cursor.fetchall()
    conexion.close()

    # Create the filtros dictionary to pass to the template
    filtros = {
        'estado': estado,
        'desde': desde,
        'hasta': hasta
    }

    return render_template('standard/standard_dashboard.html',
                         cotizaciones=cotizaciones,
                         filtros=filtros)


# --- 2. RUTAS PÚBLICAS (sin autenticación requerida) ---
@app.route('/')
def index():
    # Forzar cierre de sesión al iniciar
    session.clear()

    # Si no está autenticado o el rol no es válido, mostrar landing
    return render_template('landing.html')

    # Verificar si el usuario ya está autenticado
    if 'user_id' in session:
        if session.get('user_rol') == 'standard':
            return redirect(url_for('standard_dashboard'))
        elif session.get('user_rol') == 'admin':
            return redirect(url_for('dashboard'))

    # Si no está autenticado o el rol no es válido, mostrar landing
    return render_template('landing.html')


# ----- REGISTRO DE USUARIO -----
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        telefono = request.form.get('telefono')
        contrasena = request.form.get('contrasena')
        confirmar_contrasena = request.form.get('confirmar_contrasena')
        rol = request.form.get('rol', 'standard')  # Por defecto: standard
        pin_admin = request.form.get('pin_admin', '')

        # Validar contraseñas
        if contrasena != confirmar_contrasena:
            return "Las contraseñas no coinciden", 400

        conexion = get_db_connection()
        cursor = conexion.cursor()

        # Validar PIN si el rol es admin
        pin_id_usado = None
        if rol == 'admin':
            if not pin_admin:
                conexion.close()
                flash('El PIN de Administrador es obligatorio', 'danger')
                return redirect(url_for('registro'))
                
            cursor.execute('SELECT id, usado FROM pines_admin WHERE pin = ?', (pin_admin,))
            pin_record = cursor.fetchone()
            
            if not pin_record or pin_record[1]:
                conexion.close()
                flash('PIN inválido o ya utilizado. Adquiere una suscripción para obtener uno nuevo.', 'danger')
                return redirect(url_for('registro'))
            
            pin_id_usado = pin_record[0]

        # Guardar en la base de datos
        contrasena_hash = generate_password_hash(contrasena)
        
        from datetime import datetime, timedelta
        fecha_vencimiento = None
        if rol == 'admin':
            fecha_vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            
        try:
            cursor.execute('''
                INSERT INTO clientes (nombre, correo, telefono, contrasena, rol, fecha_vencimiento_suscripcion)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (nombre, correo, telefono, contrasena_hash, rol, fecha_vencimiento))
            nuevo_usuario_id = cursor.lastrowid
            
            # Quemar el PIN
            if pin_id_usado:
                cursor.execute('UPDATE pines_admin SET usado = 1, usado_por = ? WHERE id = ?', (nuevo_usuario_id, pin_id_usado))
                
            conexion.commit()
        except sqlite3.IntegrityError:
            conexion.rollback()
            flash('El correo electrónico ya está registrado', 'danger')
            return redirect(url_for('registro'))
        finally:
            conexion.close()

        return redirect(url_for('login'))

    # Si es GET, mostrar el formulario de registro
    return render_template('autenticacion/registro.html')  # ← ¡Asegúrate de que existe registro.html!

@app.route('/setup-superadmin')
def setup_superadmin():
    # Esta ruta es temporal para arreglar el acceso Superadmin en Render (Producción)
    try:
        from werkzeug.security import generate_password_hash
        conexion = get_db_connection()
        cursor = conexion.cursor()
        contrasena_hash = generate_password_hash('admin123')
        
        cursor.execute("SELECT id FROM clientes WHERE correo = 'admin@sistema.com'")
        user = cursor.fetchone()
        
        if user:
            # Si existe, solo le actualizamos la contraseña y el rol a superadmin
            cursor.execute("UPDATE clientes SET rol = 'superadmin', contrasena = ? WHERE correo = 'admin@sistema.com'", (contrasena_hash,))
        else:
            # Si no existe, lo creamos forzosamente (usando el formato compatible)
            cursor.execute('''
                INSERT INTO clientes (nombre, correo, telefono, rol, contrasena, activo)
                VALUES (?, ?, ?, ?, ?, TRUE)
            ''', ('Administrador Maestro', 'admin@sistema.com', '000000', 'superadmin', contrasena_hash))
            
        conexion.commit()
        conexion.close()
        return "¡Éxito! Tu cuenta de Superadmin en Render ha sido configurada. <br><br> Correo: <b>admin@sistema.com</b> <br> Contraseña: <b>admin123</b> <br><br> <a href='/login'>Ir a Iniciar Sesión</a>"
    except Exception as e:
        return f"Error configurando superadmin: {str(e)}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    tipo_login = request.args.get('tipo', 'standard')  # Valor por defecto 'standard'
    error = None

    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        tipo_login = request.form.get('tipo_login', 'standard')  # Valor por defecto 'standard'
        pin_admin = request.form.get('pin_admin', '')

        # Conexión a DB
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        
        # Obtener el cliente y el estado de su creador
        cursor.execute('''
            SELECT c.*, creador.activo as creador_activo, creador.fecha_vencimiento_suscripcion as creador_fecha_vencimiento
            FROM clientes c 
            LEFT JOIN clientes creador ON c.creador_id = creador.id 
            WHERE c.correo = ?
        ''', (correo,))
        cliente = cursor.fetchone()

        if cliente and check_password_hash(cliente['contrasena'], contrasena):
            
            # 1. Verificar si la cuenta está activa
            if not cliente['activo']:
                conexion.close()
                error = 'Tu cuenta ha sido suspendida.'
                return render_template('autenticacion/login.html', error=error, tipo=tipo_login)
                
            # 2. Verificar el Kill-Switch (si el Administrador padre está inactivo, bloquear a los vendedores)
            if cliente['creador_id'] and cliente['creador_activo'] == 0:
                conexion.close()
                error = 'La suscripción del Administrador principal ha sido suspendida. Por favor, contacta a tu superior.'
                return render_template('autenticacion/login.html', error=error, tipo=tipo_login)

            # 3. Verificar si la suscripción venció (Para Admins o Vendedores)
            from datetime import datetime
            ahora = datetime.now()

            if cliente['rol'] == 'admin' and cliente['fecha_vencimiento_suscripcion']:
                vence_str = str(cliente['fecha_vencimiento_suscripcion']).split('.')[0]
                vence = datetime.strptime(vence_str, '%Y-%m-%d %H:%M:%S')
                if ahora > vence:
                    conexion.close()
                    error = 'Tu suscripción ha vencido. Por favor, contacta a soporte para renovarla.'
                    return render_template('autenticacion/login.html', error=error, tipo=tipo_login)
                    
            if cliente['creador_id'] and cliente['creador_fecha_vencimiento']:
                vence_str = str(cliente['creador_fecha_vencimiento']).split('.')[0]
                vence = datetime.strptime(vence_str, '%Y-%m-%d %H:%M:%S')
                if ahora > vence:
                    conexion.close()
                    error = 'La suscripción del Administrador principal ha vencido. Por favor, contacta a tu superior.'
                    return render_template('autenticacion/login.html', error=error, tipo=tipo_login)

            rol = cliente['rol']

            # Registrar login exitoso
            registrar_log(
                usuario_id=cliente['id'],
                accion="login_exitoso",
                detalle={
                    "ip": request.remote_addr,
                    "user_agent": request.user_agent.string,
                    "rol": rol
                }
            )

            # Actualizar ultima_conexion
            cursor.execute('UPDATE clientes SET ultima_conexion = CURRENT_TIMESTAMP WHERE id = ?', (cliente['id'],))
            conexion.commit()
            conexion.close()

            # Guardar sesión
            session['user_id'] = cliente['id']
            session['user_nombre'] = cliente['nombre']
            session['user_rol'] = rol
            session['user_email'] = cliente['correo']

            # Redirigir según el rol
            if rol == 'superadmin':
                return redirect(url_for('dashboard')) 
            elif rol == 'admin':
                return redirect(url_for('dashboard'))
            elif rol == 'standard':
                return redirect(url_for('standard_dashboard'))
            else:
                return redirect(url_for('index'))

        else:
            conexion.close()
            error = 'Credenciales incorrectas'

    return render_template('autenticacion/login.html', error=error, tipo=tipo_login)



@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_nombre', None)
    session.pop('user_rol', None)
    return redirect('/')


# --- 3. RUTAS PROTEGIDAS (requieren autenticación) ---
@app.route('/dashboard')
@login_required
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_rol = session.get('user_rol', 'standard')

    # Redirigir usuarios standard inmediatamente
    if user_rol == 'standard':
        return redirect(url_for('standard_dashboard'))

    if user_rol == 'superadmin':
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        
        # --- MÉTRICAS SAAS PARA SUPERADMIN ---
        cursor.execute("SELECT COUNT(*) FROM clientes WHERE rol = 'admin'")
        total_admins = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM clientes WHERE rol = 'standard'")
        total_vendors = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cotizaciones")
        total_cotizaciones = cursor.fetchone()[0]
        
        # Cotizaciones recientes globales (viendo quién la hizo)
        cursor.execute('''
            SELECT c.id, c.fecha, cli.nombre as cliente, v.nombre as vendedor, c.total, c.estado
            FROM cotizaciones c
            JOIN clientes cli ON c.cliente_id = cli.id
            LEFT JOIN clientes v ON c.creador_id = v.id
            ORDER BY c.fecha DESC LIMIT 10
        ''')
        cotizaciones = cursor.fetchall()
        conexion.close()
        
        return render_template('admin/dashboard_superadmin.html',
            total_admins=total_admins,
            total_vendors=total_vendors,
            total_cotizaciones=total_cotizaciones,
            cotizaciones=cotizaciones
        )

    # Conexión a BD solo para admins

    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    cursor.execute('SELECT COUNT(*) FROM clientes')
    total_usuarios = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM productos')
    total_productos = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM cotizaciones')
    total_cotizaciones = cursor.fetchone()[0]


    # Obtener las 10 cotizaciones más recientes con datos de cliente
    cursor.execute('''
        SELECT c.id, c.fecha, cli.nombre as cliente, c.total, c.estado
        FROM cotizaciones c
        JOIN clientes cli ON c.cliente_id = cli.id
        ORDER BY c.fecha DESC
        LIMIT 10
    ''')
    actividades_recientes = cursor.fetchall()

    # Estadísticas: conteos y listados por estado
    estados = ['Aprobada', 'Pendiente', 'Rechazada']
    cotizaciones_estado = {'aprobadas': [], 'pendientes': [], 'rechazadas': []}
    cotizaciones_aprobadas = cotizaciones_pendientes = cotizaciones_rechazadas = 0

    for estado, key in zip(estados, ['aprobadas', 'pendientes', 'rechazadas']):
        if estado == 'Pendiente':
            cursor.execute('''
                SELECT c.id, c.fecha, cli.nombre as cliente, c.total
                FROM cotizaciones c
                JOIN clientes cli ON c.cliente_id = cli.id
                WHERE c.estado = ? OR c.estado = ?
                ORDER BY c.fecha DESC
            ''', (estado, 'pendiente'))
        else:
            cursor.execute('''
                SELECT c.id, c.fecha, cli.nombre as cliente, c.total
                FROM cotizaciones c
                JOIN clientes cli ON c.cliente_id = cli.id
                WHERE c.estado = ?
                ORDER BY c.fecha DESC
            ''', (estado,))
        cotizaciones_estado[key] = cursor.fetchall()
        count = len(cotizaciones_estado[key])
        if key == 'aprobadas':
            cotizaciones_aprobadas = count
        elif key == 'pendientes':
            cotizaciones_pendientes = count
        elif key == 'rechazadas':
            cotizaciones_rechazadas = count

    conexion.close()

    # Renderizar template según rol
    if user_rol == 'superadmin':
        return render_template('admin/superadmin_dashboard.html',
                           nombre=session['user_nombre'],
                           rol=user_rol,
                           total_usuarios=total_usuarios,
                           total_productos=total_productos,
                           total_cotizaciones=total_cotizaciones,
                           actividades_recientes=actividades_recientes,
                           cotizaciones_aprobadas=cotizaciones_aprobadas,
                           cotizaciones_pendientes=cotizaciones_pendientes,
                           cotizaciones_rechazadas=cotizaciones_rechazadas,
                           cotizaciones_estado=cotizaciones_estado,
                           autenticado=True)
    else:  # Rol 'admin'
        return render_template('admin/admin_dashboard.html',
                           nombre=session['user_nombre'],
                           rol=user_rol,
                           total_usuarios=total_usuarios,
                           total_productos=total_productos,
                           total_cotizaciones=total_cotizaciones,
                           actividades_recientes=actividades_recientes,
                           cotizaciones_aprobadas=cotizaciones_aprobadas,
                           cotizaciones_pendientes=cotizaciones_pendientes,
                           cotizaciones_rechazadas=cotizaciones_rechazadas,
                           cotizaciones_estado=cotizaciones_estado,
                           autenticado=True)

@app.route('/admin')
@login_required
def admin_panel():
    if session.get('user_rol') == 'superadmin':
        # Cargar datos exclusivos para superadmin
        return render_template('admin/superadmin_dashboard.html',
                             funciones_exclusivas=True)
    elif session.get('user_rol') == 'admin':
        return render_template('admin/admin_dashboard.html')  # Panel normal
    else:
        return redirect(url_for('standard_dashboard'))


# ----- CLIENTES -----
@app.route('/clientes', methods=['GET', 'POST'])
@login_required
@admin_required
def clientes():
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            razon_social = request.form.get('razon_social', '').strip()
            nit = request.form.get('nit', 'S/N').strip()
            codigo_cliente = request.form.get('codigo_cliente', '').strip()
            telefono = request.form.get('telefono', '').strip()
            referencia = request.form.get('referencia', '').strip()
            tipo_cliente = request.form.get('tipo_cliente', 'normal').strip()

            # Validaciones
            if not razon_social:
                flash('El nombre/razón social es obligatorio', 'danger')
                return redirect(url_for('clientes'))


            # Insertar nuevo cliente con el ID del admin que lo registra
            conexion = get_db_connection()
            cursor = conexion.cursor()

            # Generar código de cliente automático si no se ingresó uno
            if not codigo_cliente:
                cursor.execute("SELECT codigo_cliente FROM clientes WHERE codigo_cliente LIKE 'CLI-%'")
                codigos = cursor.fetchall()
                max_num = 0
                for row in codigos:
                    codigo = row[0]
                    if codigo:
                        try:
                            num = int(codigo.split('-')[1])
                            if num > max_num:
                                max_num = num
                        except (ValueError, IndexError):
                            pass
                codigo_cliente = f"CLI-{max_num + 1:04d}"
            else:
                # Validar que el código de cliente no se repita (si se ingresó alguno manualmente)
                cursor.execute('SELECT id FROM clientes WHERE codigo_cliente = ?', (codigo_cliente,))
                if cursor.fetchone():
                    flash('El código de cliente ya está registrado. Usa uno diferente.', 'danger')
                    conexion.close()
                    return redirect(url_for('clientes'))

            cursor.execute('''
                INSERT INTO clientes (
                    nombre, nit, codigo_cliente, telefono, referencia, 
                    tipo_cliente, creador_id, rol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                razon_social, nit, codigo_cliente, telefono,
                referencia, tipo_cliente, session['user_id'], 'cliente'
            ))

            conexion.commit()
            flash('Cliente registrado exitosamente', 'success')

        except Exception as e:
            flash(f'Error al registrar cliente: {str(e)}', 'danger')
        finally:
            if 'conexion' in locals():
                conexion.close()

        return redirect(url_for('clientes'))

    # Método GET - Mostrar lista de clientes con paginación
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()

        # Parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = 5  # Mostrar 5 clientes por página
        offset = (page - 1) * per_page
        
        busqueda = request.args.get('buscar', '').strip()

        # Consulta base diferente para superadmin
        if session.get('user_rol') == 'superadmin':
            count_query = "SELECT COUNT(*) FROM clientes WHERE rol = 'cliente'"
            query = "SELECT * FROM clientes WHERE rol = 'cliente'"
            params = []
        else:
            count_query = "SELECT COUNT(*) FROM clientes WHERE creador_id = ? AND rol = 'cliente'"
            query = "SELECT * FROM clientes WHERE creador_id = ? AND rol = 'cliente'"
            params = [session['user_id']]

        if busqueda:
            search_condition = '''
                AND (nombre LIKE ? OR 
                     nit LIKE ? OR 
                     codigo_cliente LIKE ? OR 
                     telefono LIKE ? OR 
                     referencia LIKE ?)
            '''
            count_query += search_condition
            query += search_condition
            search_param = f"%{busqueda}%"
            params.extend([search_param] * 5)

        # Obtener el total de registros para la paginación
        cursor.execute(count_query, params)
        total_clientes = cursor.fetchone()[0]
        
        # Obtener los clientes para la página actual
        query += " ORDER BY nombre LIMIT ? OFFSET ?"
        cursor.execute(query, params + [per_page, offset])
        clientes = cursor.fetchall()
        
        # Calcular el número total de páginas
        total_pages = (total_clientes + per_page - 1) // per_page

    except Exception as e:
        flash(f'Error al cargar clientes: {str(e)}', 'danger')
        clientes = []
        total_pages = 1
        page = 1
    finally:
        if 'conexion' in locals():
            conexion.close()

    # Crear diccionario de filtros para evitar errores en la plantilla
    filtros = {
        'cliente': '',
        'codigo_cliente': '',
        'desde': '',
        'hasta': '',
        'estado': ''
    }
    
    # Datos de paginación
    pagination = {
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'total_items': total_clientes if 'total_clientes' in locals() else 0
    }
    
    return render_template('clientes/clientes.html', clientes=clientes, filtros=filtros, pagination=pagination)


@app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_cliente(id):
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Verificar que el cliente pertenece al admin actual o es superadmin, y que sea realmente un cliente
    cursor.execute("SELECT creador_id FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
    cliente = cursor.fetchone()

    if not cliente or (cliente[0] != session['user_id'] and session.get('user_rol') != 'superadmin'):
        flash('No tienes permisos para editar este cliente, o no existe.', 'danger')
        return redirect(url_for('clientes'))


    if request.method == 'POST':
        # Obtener datos del formulario
        nombre = request.form['nombre']
        nit = request.form['nit']
        codigo_cliente = request.form.get('codigo_cliente', '')
        telefono = request.form.get('telefono', '')
        referencia = request.form.get('referencia', '')

        # Actualizar en la base de datos (permitir cambiar el código de cliente)
        cursor.execute('''
            UPDATE clientes SET 
                nombre = ?,
                nit = ?,
                codigo_cliente = ?,
                telefono = ?,
                referencia = ?
            WHERE id = ?
        ''', (nombre, nit, codigo_cliente, telefono, referencia, id))

        conexion.commit()
        conexion.close()
        return redirect('/clientes')

    # GET - Mostrar formulario de edición
    cursor.execute("SELECT * FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
    cliente = cursor.fetchone()
    conexion.close()

    # Crear diccionario de filtros para evitar errores en la plantilla
    filtros = {
        'cliente': '',
        'codigo_cliente': '',
        'desde': '',
        'hasta': '',
        'estado': ''
    }
    
    return render_template('clientes/editar_cliente.html', cliente=cliente, filtros=filtros)


@app.route('/clientes/eliminar/<int:id>')
@login_required
@admin_required
def eliminar_cliente(id):
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Verificar que el cliente pertenece al admin actual o es superadmin, y que sea realmente un cliente
    cursor.execute("SELECT creador_id, nombre FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
    cliente = cursor.fetchone()

    if not cliente or (cliente[0] != session['user_id'] and session.get('user_rol') != 'superadmin'):
        flash('No tienes permisos para eliminar este cliente, o no existe.', 'danger')
        return redirect(url_for('clientes'))

    # Registrar antes de eliminar
    registrar_log(
        usuario_id=session['user_id'],
        accion="eliminar_cliente",
        detalle={
            "cliente_id": id,
            "nombre_cliente": cliente[1] if cliente else "Desconocido"
        }
    )

    cursor.execute('DELETE FROM clientes WHERE id=?', (id,))
    conexion.commit()
    conexion.close()

    flash('Cliente eliminado correctamente', 'success')
    return redirect('/clientes')


# ----- API CATEGORÍAS -----
@app.route('/api/categorias', methods=['GET'])
@login_required
def api_categorias():
    """API para obtener todas las categorías"""
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        cursor.execute("SELECT id, nombre, descripcion FROM categorias WHERE activo = 1 ORDER BY nombre")
        categorias = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        categorias_list = [
            {'id': cat[0], 'nombre': cat[1], 'descripcion': cat[2]}
            for cat in categorias
        ]
        
        conexion.close()
        return jsonify(categorias_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categorias', methods=['POST'])
@login_required
def api_crear_categoria():
    """API para crear una nueva categoría"""
    try:
        data = request.get_json()
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({'success': False, 'message': 'El nombre de la categoría es requerido'})
        
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        # Verificar si la categoría ya existe
        cursor.execute("SELECT id FROM categorias WHERE nombre = ? AND activo = 1", (nombre,))
        if cursor.fetchone():
            conexion.close()
            return jsonify({'success': False, 'message': 'Ya existe una categoría con ese nombre'})
        
        # Crear la nueva categoría
        cursor.execute(
            "INSERT INTO categorias (nombre, descripcion, activo) VALUES (?, ?, 1) RETURNING id",
            (nombre, descripcion)
        )
        categoria_id = cursor.lastrowid
        conexion.commit()
        conexion.close()
        
        return jsonify({'success': True, 'categoria_id': categoria_id, 'message': 'Categoría creada exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al crear la categoría: {str(e)}'})


@app.route('/api/categorias/<int:categoria_id>', methods=['DELETE'])
@login_required
@admin_required
def api_eliminar_categoria(categoria_id):
    """API para eliminar una categoría"""
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        # Verificar si la categoría existe
        cursor.execute("SELECT nombre FROM categorias WHERE id = ? AND activo = 1", (categoria_id,))
        categoria = cursor.fetchone()
        
        if not categoria:
            conexion.close()
            return jsonify({'success': False, 'message': 'Categoría no encontrada'})
        
        # Verificar si hay productos usando esta categoría
        cursor.execute("SELECT COUNT(*) FROM productos WHERE categoria_id = ?", (categoria_id,))
        productos_usando = cursor.fetchone()[0]
        
        if productos_usando > 0:
            conexion.close()
            return jsonify({
                'success': False, 
                'message': f'No se puede eliminar la categoría "{categoria[0]}" porque está siendo utilizada por {productos_usando} producto(s)'
            })
        
        # Eliminar la categoría (marcado lógico)
        cursor.execute("UPDATE categorias SET activo = 0 WHERE id = ?", (categoria_id,))
        conexion.commit()
        conexion.close()
        
        return jsonify({'success': True, 'message': f'Categoría "{categoria[0]}" eliminada exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar la categoría: {str(e)}'})


# ----- IMPORTACIÓN DE PRODUCTOS DESDE PDF -----

@app.route('/productos/importar-pdf', methods=['POST'])
@login_required
@admin_required
def importar_pdf_productos():
    """Recibe un archivo PDF, extrae las celdas de la tabla omitiendo #, Procedencia, Cantidad y Total"""
    if 'archivo_pdf' not in request.files:
        return jsonify({'success': False, 'message': 'No se proporcionó ningún archivo PDF'}), 400

    archivo = request.files['archivo_pdf']
    consolidar = request.form.get('consolidar_duplicados', 'true').lower() == 'true'

    if archivo.filename == '' or not archivo.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'message': 'El archivo debe ser un PDF válido (.pdf)'}), 400

    try:
        pdf_bytes = archivo.read()
        raw_items = PDFProductExtractor.extract_products(pdf_bytes, consolidar_duplicados=False)
        consolidated_items = PDFProductExtractor.extract_products(pdf_bytes, consolidar_duplicados=True)
        duplicados = PDFProductExtractor.detectar_duplicados(raw_items)

        items_to_return = consolidated_items if consolidar else raw_items

        if not items_to_return:
            return jsonify({
                'success': False,
                'message': 'No se encontraron filas de productos válidos en el PDF. Verifique que el documento contenga una tabla con productos.'
            }), 422

        return jsonify({
            'success': True,
            'nombre_sugerido': os.path.splitext(archivo.filename)[0],
            'total_extraidos': len(raw_items),
            'total_unicos': len(consolidated_items),
            'duplicados': duplicados,
            'has_duplicates': len(duplicados) > 0,
            'consolidar_activo': consolidar,
            'products': items_to_return
        })

    except Exception as e:
        app.logger.error(f"Error procesando PDF: {e}")
        return jsonify({'success': False, 'message': f'Error procesando el PDF: {str(e)}'}), 500


@app.route('/productos/pegar-texto', methods=['POST'])
@login_required
@admin_required
def procesar_texto_pegado():
    """Recibe texto copiado/pegado directamente por el usuario de una tabla y extrae los productos"""
    try:
        data = request.get_json() or {}
        texto = data.get('texto', '').strip()
        consolidar = data.get('consolidar_duplicados', True)

        if not texto:
            return jsonify({'success': False, 'message': 'No se proporcionó ningún texto para procesar'}), 400

        raw_items = PDFProductExtractor.parse_pasted_text(texto, consolidar_duplicados=False)
        consolidated_items = PDFProductExtractor.parse_pasted_text(texto, consolidar_duplicados=True)
        duplicados = PDFProductExtractor.detectar_duplicados(raw_items)

        items_to_return = consolidated_items if consolidar else raw_items

        if not items_to_return:
            return jsonify({
                'success': False,
                'message': 'No se identificaron filas de productos en el texto pegado. Asegúrese de incluir las filas de la tabla.'
            }), 422

        return jsonify({
            'success': True,
            'total_extraidos': len(raw_items),
            'total_unicos': len(consolidated_items),
            'duplicados': duplicados,
            'has_duplicates': len(duplicados) > 0,
            'consolidar_activo': consolidar,
            'products': items_to_return
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error procesando el texto: {str(e)}'}), 500




@app.route('/productos/guardar-importacion', methods=['POST'])

@login_required
@admin_required
def guardar_importacion_route():
    """Guarda un lote de importación con su nombre y sus items editados"""
    try:
        data = request.get_json() or {}
        nombre_importacion = data.get('nombre_importacion', '').strip()
        items = data.get('items', [])

        if not items:
            return jsonify({'success': False, 'message': 'No hay productos para guardar en la importación'}), 400

        importacion_id, nombre_final = guardar_importacion_pdf(
            nombre_importacion=nombre_importacion,
            items=items,
            usuario_id=session.get('user_id')
        )

        return jsonify({
            'success': True,
            'importacion_id': importacion_id,
            'nombre_importacion': nombre_final,
            'message': f'Importación "{nombre_final}" guardada exitosamente en el historial.'
        })


    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al guardar importación: {str(e)}'}), 500


@app.route('/productos/importaciones', methods=['GET'])
@login_required
def listar_importaciones():
    """Retorna la lista de importaciones guardadas"""
    try:
        importaciones = obtener_importaciones_pdf()
        return jsonify({'success': True, 'importaciones': importaciones})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/productos/importacion/<int:importacion_id>', methods=['GET'])
@login_required
def detalle_importacion(importacion_id):
    """Retorna los datos de una importación guardada y sus items"""
    try:
        imp, items = obtener_importacion_por_id(importacion_id)
        if not imp:
            return jsonify({'success': False, 'message': 'Importación no encontrada'}), 404
        return jsonify({'success': True, 'importacion': imp, 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/productos/importacion/<int:importacion_id>', methods=['DELETE'])
@login_required
@admin_required
def eliminar_importacion_route(importacion_id):
    """Elimina una importación guardada y sus items del historial"""
    try:
        eliminar_importacion_pdf(importacion_id)
        return jsonify({'success': True, 'message': 'Importación eliminada correctamente del historial.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar la importación: {str(e)}'}), 500



@app.route('/productos/registrar-seleccionados', methods=['POST'])
@login_required
@admin_required
def registrar_seleccionados_route():
    """Registra los productos seleccionados de la importación en el catálogo oficial de productos"""
    try:
        data = request.get_json() or {}
        items = data.get('items', [])
        empresa = data.get('empresa', 'General').strip() or 'General'
        categoria_id = data.get('categoria_id')
        respetar_cantidades = data.get('respetar_cantidades', True)

        if not items:
            return jsonify({'success': False, 'message': 'No se seleccionó ningún producto para registrar'}), 400

        count = registrar_productos_seleccionados(
            items=items,
            empresa=empresa,
            categoria_id=categoria_id,
            respetar_cantidades=respetar_cantidades
        )

        return jsonify({
            'success': True,
            'count': count,
            'message': f'Se registraron/actualizaron exitosamente {count} producto(s) en el catálogo registrado.'
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al registrar productos: {str(e)}'}), 500



# ----- PRODUCTOS -----
@app.route('/productos', methods=['GET', 'POST'])
@login_required
@admin_required
def productos():
    mensaje_error = None

    # Manejo del formulario POST (registro de nuevos productos)
    if request.method == 'POST':
        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                
                empresa = request.form['empresa']
                codigo = request.form['codigo']
                descripcion = request.form['descripcion']
                marca = request.form['marca']
                tm = request.form['tm']
                um = request.form['um']
                cantidad = int(request.form['cantidad'])
                precio_unitario = float(request.form['precio_unitario'])
                precio_total = cantidad * precio_unitario
                categoria_id = request.form.get('categoria_id')

                # Validar si ya existe combinación empresa + codigo
                cursor.execute("SELECT COUNT(*) FROM productos WHERE empresa=? AND codigo=?", (empresa, codigo))
                existe = cursor.fetchone()[0]

                if existe > 0:
                    mensaje_error = f"⚠️ El código '{codigo}' ya existe para la empresa '{empresa}'."
                else:
                    cursor.execute("PRAGMA table_info(productos)")
                    columnas = cursor.fetchall()
                    columnas_nombres = [col[1] for col in columnas]
                    
                    categoria_nombre = None
                    if categoria_id:
                        cursor.execute("SELECT nombre FROM categorias WHERE id = ?", (categoria_id,))
                        resultado = cursor.fetchone()
                        if resultado:
                            categoria_nombre = resultado[0]

                    if 'es_importado' in columnas_nombres:
                        cursor.execute('''
                            INSERT INTO productos 
                            (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria, es_importado)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        ''', (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria_nombre))
                    else:
                        cursor.execute('''
                            INSERT INTO productos 
                            (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria_nombre))
                    
                    conexion.commit()

        except Exception as e:
            mensaje_error = f"Error al registrar el producto: {str(e)}"

    # Lógica de búsqueda
    empresa = request.args.get('empresa', '')
    codigo = request.args.get('codigo', '')
    descripcion = request.args.get('descripcion', '')
    marca = request.args.get('marca', '')
    categoria = request.args.get('categoria', '')
    tab_activa = request.args.get('tab', 'registrados')
    
    # Paginación independiente para ambas tablas
    page_reg = request.args.get('page_reg', request.args.get('page', 1, type=int), type=int)
    page_imp = request.args.get('page_imp', 1, type=int)
    per_page = 5

    columnas_nombres = []
    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            cursor.execute("PRAGMA table_info(productos)")
            columnas = cursor.fetchall()
            columnas_nombres = [col[1] for col in columnas]

        if 'categoria_id' in columnas_nombres:
            base_query = "SELECT p.*, c.nombre as categoria_nombre FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id WHERE 1=1"
            count_query = "SELECT COUNT(*) FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id WHERE 1=1"
            use_alias = True
        else:
            base_query = "SELECT *, categoria as categoria_nombre FROM productos WHERE 1=1"
            count_query = "SELECT COUNT(*) FROM productos WHERE 1=1"
            use_alias = False
    except Exception as e:
        base_query = "SELECT * FROM productos WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM productos WHERE 1=1"
        use_alias = False

    filter_sql = ""
    params = []

    if empresa:
        filter_sql += " AND p.empresa LIKE ?" if use_alias else " AND empresa LIKE ?"
        params.append(f"%{empresa}%")
    if codigo:
        filter_sql += " AND p.codigo LIKE ?" if use_alias else " AND codigo LIKE ?"
        params.append(f"%{codigo}%")
    if descripcion:
        filter_sql += " AND p.descripcion LIKE ?" if use_alias else " AND descripcion LIKE ?"
        params.append(f"%{descripcion}%")
    if marca:
        filter_sql += " AND p.marca LIKE ?" if use_alias else " AND marca LIKE ?"
        params.append(f"%{marca}%")
    if categoria:
        if 'categoria_id' in columnas_nombres:
            filter_sql += " AND p.categoria_id = ?"
        else:
            filter_sql += " AND categoria LIKE ?"
        params.append(categoria)

    # 1. Consultar Productos Registrados (Manuales: es_importado = 0 o NULL)
    cond_reg = " AND (p.es_importado IS NULL OR p.es_importado = 0)" if use_alias else " AND (es_importado IS NULL OR es_importado = 0)"
    offset_reg = (page_reg - 1) * per_page

    # 2. Consultar Productos Importados (PDF/Texto: es_importado = 1)
    cond_imp = " AND p.es_importado = 1" if use_alias else " AND es_importado = 1"
    offset_imp = (page_imp - 1) * per_page

    productos_registrados = []
    total_registrados = 0
    total_pages_reg = 1

    productos_importados = []
    total_importados = 0
    total_pages_imp = 1

    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()

            # Registrados
            cursor.execute(count_query + filter_sql + cond_reg, params)
            total_registrados = cursor.fetchone()[0]
            total_pages_reg = max(1, (total_registrados + per_page - 1) // per_page)
            cursor.execute(base_query + filter_sql + cond_reg + " ORDER BY empresa, codigo LIMIT ? OFFSET ?", params + [per_page, offset_reg])
            productos_registrados = cursor.fetchall()

            # Importados
            cursor.execute(count_query + filter_sql + cond_imp, params)
            total_importados = cursor.fetchone()[0]
            total_pages_imp = max(1, (total_importados + per_page - 1) // per_page)
            cursor.execute(base_query + filter_sql + cond_imp + " ORDER BY empresa, codigo LIMIT ? OFFSET ?", params + [per_page, offset_imp])
            productos_importados = cursor.fetchall()

    except Exception as e:
        mensaje_error = f"Error al buscar productos: {str(e)}"

    filtros = {
        'empresa': empresa,
        'codigo': codigo,
        'descripcion': descripcion,
        'marca': marca,
        'categoria': categoria
    }

    pagination_reg = {
        'page': page_reg,
        'per_page': per_page,
        'total_pages': total_pages_reg,
        'total_items': total_registrados
    }

    pagination_imp = {
        'page': page_imp,
        'per_page': per_page,
        'total_pages': total_pages_imp,
        'total_items': total_importados
    }

    # Obtener clientes para el modal de PDF Directo
    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            if session.get('user_rol') == 'superadmin':
                cursor.execute("SELECT id, nombre FROM clientes WHERE rol = 'cliente' ORDER BY nombre")
            else:
                cursor.execute("SELECT id, nombre FROM clientes WHERE creador_id = ? AND rol = 'cliente' ORDER BY nombre", 
                               (session['user_id'],))
            clientes = cursor.fetchall()
    except Exception:
        clientes = []

    return render_template(
        'productos/productos.html',
        productos=productos_registrados,
        productos_registrados=productos_registrados,
        productos_importados=productos_importados,
        mensaje_error=mensaje_error,
        filtros=filtros,
        pagination=pagination_reg,
        pagination_reg=pagination_reg,
        pagination_imp=pagination_imp,
        tab_activa=tab_activa,
        clientes=clientes
    )



@app.route('/productos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_producto(id):
    tab = request.form.get('tab', request.args.get('tab', 'registrados'))
    page_reg = request.form.get('page_reg', request.args.get('page_reg', 1))
    page_imp = request.form.get('page_imp', request.args.get('page_imp', 1))
    
    empresa_filtro = request.form.get('empresa_filtro', request.args.get('empresa', ''))
    codigo_filtro = request.form.get('codigo_filtro', request.args.get('codigo', ''))
    descripcion_filtro = request.form.get('descripcion_filtro', request.args.get('descripcion', ''))
    marca_filtro = request.form.get('marca_filtro', request.args.get('marca', ''))
    categoria_filtro = request.form.get('categoria_filtro', request.args.get('categoria', ''))

    if request.method == 'POST':
        try:
            empresa = request.form['empresa']
            codigo = request.form['codigo']
            descripcion = request.form['descripcion']
            marca = request.form['marca']
            tm = request.form['tm']
            um = request.form['um']
            cantidad = int(request.form['cantidad'])
            precio_unitario = float(request.form['precio_unitario'])
            precio_total = cantidad * precio_unitario
            categoria_id = request.form.get('categoria_id')
            
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                
                categoria_nombre = None
                if categoria_id:
                    cursor.execute("SELECT nombre FROM categorias WHERE id = ?", (categoria_id,))
                    resultado = cursor.fetchone()
                    if resultado:
                        categoria_nombre = resultado[0]
                
                cursor.execute("PRAGMA table_info(productos)")
                columnas = cursor.fetchall()
                columnas_nombres = [col[1] for col in columnas]
                
                if 'categoria_id' in columnas_nombres:
                    cursor.execute('''
                        UPDATE productos SET
                            empresa=?, codigo=?, descripcion=?, marca=?, tm=?, um=?, 
                            cantidad=?, precio_unitario=?, precio_total=?, categoria_id=?, categoria=?
                        WHERE id=?
                    ''', (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria_nombre, id))
                else:
                    cursor.execute('''
                        UPDATE productos SET
                            empresa=?, codigo=?, descripcion=?, marca=?, tm=?, um=?, 
                            cantidad=?, precio_unitario=?, precio_total=?, categoria=?
                        WHERE id=?
                    ''', (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_nombre, id))
                
                conexion.commit()
            
            flash('Producto actualizado correctamente', 'success')
            return redirect(url_for('productos', tab=tab, page_reg=page_reg, page_imp=page_imp, empresa=empresa_filtro, codigo=codigo_filtro, descripcion=descripcion_filtro, marca=marca_filtro, categoria=categoria_filtro))
        
        except Exception as e:
            flash(f'Error al actualizar el producto: {str(e)}', 'danger')
            return redirect(url_for('editar_producto', id=id, tab=tab, page_reg=page_reg, page_imp=page_imp, empresa=empresa_filtro, codigo=codigo_filtro, descripcion=descripcion_filtro, marca=marca_filtro, categoria=categoria_filtro))

    # GET - Mostrar formulario de edición
    with get_db_connection() as conexion:
        cursor = conexion.cursor()
        
        cursor.execute('SELECT * FROM productos WHERE id=?', (id,))
        producto = cursor.fetchone()
        
        cursor.execute('''
            SELECT DISTINCT c.id, c.nombre 
            FROM categorias c 
            INNER JOIN productos p ON c.id = p.categoria_id 
            ORDER BY c.nombre
        ''')
        categorias_en_uso = cursor.fetchall()
        
        cursor.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
        todas_categorias = cursor.fetchall()
        
        categorias = categorias_en_uso if categorias_en_uso else todas_categorias
    
    filtros = {
        'empresa': empresa_filtro,
        'codigo': codigo_filtro,
        'descripcion': descripcion_filtro,
        'marca': marca_filtro,
        'categoria': categoria_filtro
    }

    return render_template(
        'productos/editar_producto.html',
        producto=producto,
        categorias=categorias,
        todas_categorias=todas_categorias,
        tab=tab,
        page_reg=page_reg,
        page_imp=page_imp,
        filtros=filtros
    )


    return render_template('productos/editar_producto.html', producto=producto, categorias=categorias, filtros=filtros, page=page)


@app.route('/productos/eliminar/<int:id>')
@login_required
def eliminar_producto(id):
    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            cursor.execute('DELETE FROM productos WHERE id=?', (id,))
            conexion.commit()
        flash('Producto eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar el producto: {str(e)}', 'danger')
    return redirect('/productos')


# ----- API BÚSQUEDA DE PRODUCTOS -----
@app.route('/api/buscar_productos_cotizacion', methods=['GET'])
@login_required
def buscar_productos_cotizacion():
    try:
        # Obtener parámetros de búsqueda
        empresa = request.args.get('empresa', '').strip()
        codigo = request.args.get('codigo', '').strip()
        descripcion = request.args.get('descripcion', '').strip()
        marca = request.args.get('marca', '').strip()
        categoria = request.args.get('categoria', '').strip()
        tipo_producto = request.args.get('tipo_producto', 'registrados').strip()

        # Construir la consulta SQL base
        query = '''
            SELECT p.*, c.nombre as categoria_nombre 
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id 
            WHERE 1=1
        '''
        params = []

        # Filtrar por tipo de producto (registrados vs importados)
        if tipo_producto == 'importados':
            query += ' AND (p.es_importado = 1)'
        elif tipo_producto == 'registrados':
            query += ' AND (p.es_importado IS NULL OR p.es_importado = 0)'

        # Añadir condiciones según los filtros
        if empresa:
            query += ' AND p.empresa LIKE ?'
            params.append(f'%{empresa}%')
        if codigo:
            query += ' AND p.codigo LIKE ?'
            params.append(f'%{codigo}%')
        if descripcion:
            query += ' AND p.descripcion LIKE ?'
            params.append(f'%{descripcion}%')
        if marca:
            query += ' AND p.marca LIKE ?'
            params.append(f'%{marca}%')
        if categoria:
            try:
                categoria_id = int(categoria)
                if categoria_id > 0:  # Solo aplicar filtro si es un ID válido
                    query += ' AND p.categoria_id = ?'
                    params.append(categoria_id)
            except ValueError:
                pass  # Si no es un número válido, ignorar el filtro de categoría

        # Ordenar por empresa y código
        query += ' ORDER BY p.empresa, p.codigo LIMIT 100'

        # Ejecutar la consulta
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            productos = cursor.fetchall()

            # Convertir a lista de diccionarios
            productos_list = []
            for producto in productos:
                productos_list.append({
                    'id': producto['id'],
                    'codigo': producto['codigo'],
                    'descripcion': producto['descripcion'],
                    'marca': producto['marca'],
                    'empresa': producto['empresa'],
                    'um': producto['um'],
                    'cantidad': producto['cantidad'],
                    'precio_unitario': float(producto['precio_unitario']),
                    'categoria': producto['categoria_nombre']
                })

            return jsonify({
                'success': True,
                'productos': productos_list
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


        return jsonify({'success': True, 'productos': productos_list})
        app.logger.error(f"Error en búsqueda de productos: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cotizaciones/pdf_directo_importacion', methods=['POST'])
@login_required
def pdf_directo_importacion():
    try:
        if request.is_json:
            data = request.json
        else:
            data_str = request.form.get('data')
            if not data_str:
                return "No data provided", 400
            import json
            data = json.loads(data_str)

        items = data.get('items', [])
        descuento_porcentaje = float(data.get('descuento_porcentaje', 0.0))
        nombre_cliente = data.get('nombre_cliente', 'Cliente (PDF Directo)')
        cliente_id = data.get('cliente_id')

        if not items:
            if request.is_json:
                return jsonify({'success': False, 'message': 'No hay ítems para generar el PDF'})
            return "No hay ítems para generar el PDF", 400

        # Calcular totales
        subtotal_bruto = sum((float(item.get('cantidad', 1)) * float(item.get('precio_unitario', 0.0))) for item in items)
        monto_descuento = subtotal_bruto * (descuento_porcentaje / 100.0)
        total_final = max(0, subtotal_bruto - monto_descuento)

        def numero_a_palabras(numero):
            try:
                if numero is None:
                    return "CERO BOLIVIANOS"
                parte_entera = int(numero)
                parte_decimal = int(round((numero - parte_entera) * 100))
                palabras_entera = num2words(parte_entera, lang='es').upper()
                palabras_decimal = num2words(parte_decimal, lang='es').upper()
                resultado = f"{palabras_entera} BOLIVIANOS"
                if parte_decimal > 0:
                    resultado += f" CON {palabras_decimal} CENTAVOS"
                return resultado
            except Exception:
                return "CERO BOLIVIANOS"

        total_letras = numero_a_palabras(total_final)
        fecha_cotizacion = datetime.now().strftime("%d/%m/%Y")

        # Cargar imagen de fondo
        fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
        fondo_base64 = ""
        if os.path.exists(fondo_path):
            try:
                with open(fondo_path, "rb") as image_file:
                    fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"
            except Exception:
                pass

        # Construir datos de cliente seleccionado si existe
        cliente_data = {
            'nombre': nombre_cliente,
            'telefono': "S/N",
            'email': "S/N",
            'nit': "S/N"
        }
        
        if cliente_id:
            try:
                conn_c = get_db_connection()
                cur_c = conn_c.cursor()
                cur_c.execute('SELECT nombre, nit, telefono, correo FROM clientes WHERE id = ?', (cliente_id,))
                crow = cur_c.fetchone()
                conn_c.close()
                if crow:
                    cliente_data['nombre'] = crow[0] or cliente_data['nombre']
                    cliente_data['nit'] = crow[1] or "S/N"
                    cliente_data['telefono'] = crow[2] or "S/N"
                    cliente_data['email'] = crow[3] or "S/N"
            except Exception:
                pass

        # Construir datos de usuario
        usuario = {
            'nombre': session.get('user_nombre', 'Usuario del sistema'),
            'telefono': session.get('user_telefono', None),
            'email': session.get('user_email', None)
        }
        if not usuario.get('telefono') and session.get('user_id'):
            try:
                conn_u = get_db_connection()
                cur_u = conn_u.cursor()
                cur_u.execute('SELECT nombre, telefono, correo FROM clientes WHERE id = ?', (session.get('user_id'),))
                urow = cur_u.fetchone()
                conn_u.close()
                if urow:
                    usuario['nombre'] = urow[0] or usuario['nombre']
                    usuario['telefono'] = urow[1] or usuario['telefono']
                    usuario['email'] = urow[2] or usuario['email']
            except Exception:
                pass

        productos_formateados = []
        for item in items:
            qty = float(item.get('cantidad', 0))
            price = float(item.get('precio_unitario', 0.0))
            productos_formateados.append({
                'codigo': item.get('codigo', 'S/N'),
                'descripcion': item.get('descripcion', 'Producto'),
                'marca': item.get('marca', 'S/M'),
                'procedencia': item.get('procedencia', 'Taiwán'),
                'cantidad': qty,
                'um': item.get('um', 'UN'),
                'precio_unitario': price,
                'subtotal': qty * price
            })

        datos = {
            'cliente': cliente_data,
            'cotizacion': {
                'solicitud_numero': "Directo",
                'fecha': fecha_cotizacion,
            },
            'productos': productos_formateados,
            'subtotal': subtotal_bruto,
            'descuento': f"{descuento_porcentaje:.2f}",
            'descuento_porcentaje': descuento_porcentaje,
            'monto_descuento': monto_descuento,
            'total': total_final,
            'total_letras': total_letras,
            'usuario_sesion': session.get('user_nombre', 'Usuario del sistema'),
            'usuario': usuario,
            'logo_base64': "",
            'fondo_base64': None  # El fondo se aplicará por página después con PyPDF2
        }

        # Generar el HTML
        html_renderizado = render_template('cotizaciones/cotizacion_pdf.html', **datos)
        
        # Buscar path de wkhtmltopdf
        wkhtmltopdf_path = None
        if os.name == "nt":
            possible_paths = [
                r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
                r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    wkhtmltopdf_path = path
                    break
        else:
            import subprocess
            try:
                wkhtmltopdf_path = subprocess.check_output(['which', 'wkhtmltopdf']).decode().strip()
            except:
                wkhtmltopdf_path = '/usr/local/bin/wkhtmltopdf'

        # Generar PDF real usando la lógica de wkhtmltopdf y PyPDF2 (idéntica a pdf_cotizacion)
        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        options = {
            'enable-local-file-access': None,
            'encoding': 'UTF-8',
            'quiet': '',
            'margin-top': '10mm',
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
        }

        try:
            # Generar PDF base
            pdf_sin_fondo = pdfkit.from_string(html_renderizado, False, configuration=config, options=options)
            
            # Verificar páginas y aplicar fondo dinámico
            temp_reader = PdfReader(io.BytesIO(pdf_sin_fondo))
            num_pages = len(temp_reader.pages)
            
            if num_pages > 1:
                pdf_con_fondos = generar_pdf_margenes_dinamicos(html_renderizado, config, "directo")
            else:
                pdf_con_fondos = aplicar_fondos_por_pagina(pdf_sin_fondo)

            response = make_response(pdf_con_fondos)
            response.headers['Content-Type'] = 'application/pdf'
            # "inline" en lugar de "attachment" para que se visualice en la pestaña del navegador
            response.headers['Content-Disposition'] = 'inline; filename=cotizacion_directa.pdf'
            
            return response
            
        except OSError as e:
            print(f"Error con wkhtmltopdf en PDF Directo: {e}")
            return f"Error al generar PDF: No se encontró wkhtmltopdf", 500

    except Exception as e:
        print(f"Error general en PDF directo: {e}")
        if request.is_json:
            return jsonify({'success': False, 'message': str(e)})
        else:
            return f"Error generando PDF: {str(e)}", 500

# --- VISTA PREVIA COTIZACION -----
@app.route('/cotizaciones', methods=['GET', 'POST'])
@login_required
def gestion_cotizaciones():
    if request.method == 'POST':
        return guardar_cotizacion()
    else:
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row  # Para acceder a columnas por nombre
        cursor = conexion.cursor()
        
        # Obtener todas las categorías
        cursor.execute("SELECT id, nombre FROM categorias WHERE activo = 1 ORDER BY nombre")
        categorias = cursor.fetchall()

        # Obtener parámetros de filtro
        cliente = request.args.get('cliente', '')
        codigo_cliente = request.args.get('codigo_cliente', '')
        desde = request.args.get('desde', '')
        hasta = request.args.get('hasta', '')

        # Paginación de clientes para el dropdown
        clientes_per_page = 5
        page_cliente = int(request.args.get('page_cliente', 1))
        offset_cliente = (page_cliente - 1) * clientes_per_page
        if session.get('user_rol') == 'superadmin':
            cursor.execute("SELECT COUNT(*) FROM clientes WHERE rol = 'cliente'")
            total_clientes = cursor.fetchone()[0]
            cursor.execute("SELECT * FROM clientes WHERE rol = 'cliente' ORDER BY nombre LIMIT ? OFFSET ?", 
                           (clientes_per_page, offset_cliente))
        else:
            cursor.execute("SELECT COUNT(*) FROM clientes WHERE creador_id = ? AND rol = 'cliente'", 
                           (session['user_id'],))
            total_clientes = cursor.fetchone()[0]
            cursor.execute("SELECT * FROM clientes WHERE creador_id = ? AND rol = 'cliente' ORDER BY nombre LIMIT ? OFFSET ?", 
                           (session['user_id'], clientes_per_page, offset_cliente))
    clientes = cursor.fetchall()
    total_pages_clientes = (total_clientes + clientes_per_page - 1) // clientes_per_page

    # Paginación de productos para el catálogo

    productos_per_page = 10
    page_producto = int(request.args.get('page_producto', 1))
    tipo_producto = request.args.get('tipo_producto', 'registrados')
    offset_producto = (page_producto - 1) * productos_per_page

    cursor.execute("SELECT COUNT(*) FROM productos WHERE (es_importado IS NULL OR es_importado = 0)")
    total_registrados = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM productos WHERE es_importado = 1")
    total_importados = cursor.fetchone()[0]

    if tipo_producto == 'importados':
        cursor.execute("SELECT * FROM productos WHERE es_importado = 1 ORDER BY empresa, codigo LIMIT ? OFFSET ?", (productos_per_page, offset_producto))
        total_productos = total_importados
    else:
        cursor.execute("SELECT * FROM productos WHERE (es_importado IS NULL OR es_importado = 0) ORDER BY empresa, codigo LIMIT ? OFFSET ?", (productos_per_page, offset_producto))
        total_productos = total_registrados

    productos = cursor.fetchall()
    total_pages_productos = max(1, (total_productos + productos_per_page - 1) // productos_per_page)

    # Si es una solicitud AJAX, devolver solo la tabla de productos y paginación
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'productos': [{
                'id': p[0],
                'empresa': p[1],
                'codigo': p[2],
                'descripcion': p[3],
                'marca': p[4],
                'um': p[6],
                'cantidad': p[7],
                'precio_unitario': float(p[8]),
                'cantidad_total': p[7] if session.get('user_rol') == 'superadmin' else None
            } for p in productos],
            'page_producto': page_producto,
            'total_pages_productos': total_pages_productos
        })

    # Paginación de cotizaciones registradas
    cotizaciones_per_page = 5
    page_cotizacion = int(request.args.get('page_cotizacion', 1))
    offset_cotizacion = (page_cotizacion - 1) * cotizaciones_per_page

    if session.get('user_rol') == 'superadmin':
        cursor.execute('SELECT COUNT(*) FROM cotizaciones')
        total_cotizaciones = cursor.fetchone()[0]
        query = '''
            SELECT c.id, c.fecha, c.total, c.estado, cli.nombre, cli.codigo_cliente
            FROM cotizaciones c
            JOIN clientes cli ON c.cliente_id = cli.id
            ORDER BY c.fecha DESC
            LIMIT ? OFFSET ?
        '''
        params = [cotizaciones_per_page, offset_cotizacion]
    else:
        cursor.execute('SELECT COUNT(*) FROM cotizaciones WHERE creador_id = ?', (session['user_id'],))
        total_cotizaciones = cursor.fetchone()[0]
        query = '''
            SELECT c.id, c.fecha, c.total, c.estado, cli.nombre, cli.codigo_cliente
            FROM cotizaciones c
            JOIN clientes cli ON c.cliente_id = cli.id
            WHERE c.creador_id = ?
            ORDER BY c.fecha DESC
            LIMIT ? OFFSET ?
        '''
        params = [session['user_id'], cotizaciones_per_page, offset_cotizacion]

    cursor.execute(query, params)
    cotizaciones = cursor.fetchall()
    total_pages_cotizaciones = (total_cotizaciones + cotizaciones_per_page - 1) // cotizaciones_per_page
    conexion.close()

    # Crear diccionario de filtros para pasar a la plantilla
    filtros = {
        'cliente': cliente,
        'codigo_cliente': codigo_cliente,
        'desde': desde,
        'hasta': hasta
    }

    return render_template('cotizaciones/cotizaciones.html', 
        cotizaciones=cotizaciones,
        clientes=clientes,
        productos=productos,
        categorias=categorias,
        filtros=filtros,
        page_cliente=page_cliente,
        total_pages_clientes=total_pages_clientes,
        page_producto=page_producto,
        total_pages_productos=total_pages_productos,
        page_cotizacion=page_cotizacion,
        total_pages_cotizaciones=total_pages_cotizaciones,
        total_registrados=total_registrados,
        total_importados=total_importados,
        tipo_producto=tipo_producto)


# Reemplazar procesar_cotizacion() con esta versión mejorada

def guardar_cotizacion():
    """Versión reestructurada del guardado de cotizaciones"""
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # segundos

    # Validación inicial
    if not all(key in request.form for key in ['cliente_id', 'producto_id[]', 'cantidad[]', 'precio_unitario[]']):
        flash('Datos incompletos en el formulario', 'danger')
        return redirect(url_for('gestion_cotizaciones'))

    # Preparar datos
    cliente_id = request.form['cliente_id']
    items = zip(
        request.form.getlist('producto_id[]'),
        request.form.getlist('cantidad[]'),
        request.form.getlist('precio_unitario[]')
    )

    # Validar stock y cálculos preliminares
    try:
        productos_cotizacion = []
        total = 0.0

        for producto_id, cantidad_str, precio_str in items:
            producto_id = int(producto_id)
            cantidad = int(cantidad_str)
            precio = float(precio_str)

            if cantidad <= 0 or precio < 0:
                raise ValueError("Valores inválidos en cantidades o precios")

            subtotal = cantidad * precio
            productos_cotizacion.append((producto_id, cantidad, precio, subtotal))
            total += subtotal

    except (ValueError, TypeError) as e:
        flash('Datos numéricos inválidos en el formulario', 'danger')
        return redirect(url_for('gestion_cotizaciones'))

    # Intento de guardado con reintentos
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:  # Usar el context manager existente
                cursor = conn.cursor()

                # Iniciar transacción explícita
                cursor.execute("BEGIN IMMEDIATE TRANSACTION")

                # 1. Verificar stock (excepto para superadmin)
                if session.get('user_rol') != 'superadmin':
                    for producto_id, cantidad, _, _ in productos_cotizacion:
                        cursor.execute("SELECT cantidad, codigo FROM productos WHERE id=?", (producto_id,))
                        producto = cursor.fetchone()
                        if not producto or (producto['cantidad'] is not None and producto['cantidad'] < cantidad):
                            conn.rollback()
                            codigo_p = producto['codigo'] if producto else str(producto_id)
                            flash(f"Stock insuficiente para producto {codigo_p}", 'danger')
                            return redirect(url_for('gestion_cotizaciones'))

                # 2. Insertar cabecera de cotización
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    descuento_porcentaje = float(request.form.get('descuento_porcentaje', 0.0) or 0.0)
                except (ValueError, TypeError):
                    descuento_porcentaje = 0.0

                subtotal_bruto = total
                monto_descuento = round(subtotal_bruto * (descuento_porcentaje / 100.0), 2)
                total_final = max(0.0, round(subtotal_bruto - monto_descuento, 2))

                cursor.execute(
                    """INSERT INTO cotizaciones 
                       (cliente_id, creador_id, fecha, total, descuento_porcentaje, descuento_monto, subtotal) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cliente_id, session['user_id'], fecha, total_final, descuento_porcentaje, monto_descuento, subtotal_bruto)
                )
                cotizacion_id = cursor.lastrowid

                # 3. Insertar items
                for producto_id, cantidad, precio, subtotal in productos_cotizacion:
                    cursor.execute(
                        """INSERT INTO cotizacion_productos 
                        (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                        VALUES (?, ?, ?, ?, ?) RETURNING id""",
                        (cotizacion_id, producto_id, cantidad, precio, subtotal)
                    )

                    # 4. Actualizar stock (excepto superadmin)
                    if session.get('user_rol') != 'superadmin':
                        cursor.execute(
                            "UPDATE productos SET cantidad = cantidad - ? WHERE id = ?",
                            (cantidad, producto_id)
                        )

                # 5. Registrar en logs
                registrar_log(
                    usuario_id=session['user_id'],
                    accion="crear_cotizacion",
                    detalle={
                        "cotizacion_id": cotizacion_id,
                        "total": total,
                        "productos": len(productos_cotizacion)
                    }
                )

                conn.commit()
                flash('Cotización creada exitosamente', 'success')
                return redirect(url_for('gestion_cotizaciones', exito=True))

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            flash('Error de base de datos al guardar la cotización', 'danger')
            app.logger.error(f"Error en guardar_cotizacion (intento {attempt + 1}): {str(e)}")
            return redirect(url_for('gestion_cotizaciones'))

        except Exception as e:
            flash('Error inesperado al guardar la cotización', 'danger')
            app.logger.error(f"Error inesperado en guardar_cotizacion: {str(e)}")
            return redirect(url_for('gestion_cotizaciones'))

    flash('No se pudo completar la operación después de varios intentos', 'danger')
    return redirect(url_for('gestion_cotizaciones'))

# Ruta para ver detalles de cotización
@app.route('/cotizaciones/<int:id>')
@login_required
def ver_cotizacion(id):
    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row  # Para acceso por nombre de columna
    cursor = conexion.cursor()

    try:
        # Obtener información básica de la cotización
        cursor.execute('''
            SELECT 
                cotizaciones.id, 
                clientes.nombre,
                clientes.correo,
                clientes.telefono,
                'No disponible' as direccion, -- Valor por defecto ya que la columna no existe
                cotizaciones.fecha, 
                cotizaciones.total,
                cotizaciones.estado,
                clientes.codigo_cliente,
                creador.nombre AS creador_nombre
            FROM cotizaciones
            JOIN clientes ON cotizaciones.cliente_id = clientes.id
            JOIN clientes AS creador ON cotizaciones.creador_id = creador.id
            WHERE cotizaciones.id = ?
        ''', (id,))
        cotizacion = cursor.fetchone()

        if not cotizacion:
            flash('Cotización no encontrada', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

        # Obtener productos de la cotización
        cursor.execute('''
            SELECT 
                productos.descripcion,
                cp.cantidad,
                cp.precio_unitario,
                cp.subtotal
            FROM cotizacion_productos cp
            JOIN productos ON cp.producto_id = productos.id
            WHERE cp.cotizacion_id = ?
            ORDER BY cp.id
        ''', (id,))
        productos = cursor.fetchall()

        # Registrar acceso en el log de auditoría
        registrar_log(
            usuario_id=session['user_id'],
            accion="ver_cotizacion",
            detalle={"cotizacion_id": id}
        )

        # Crear un diccionario completo de filtros para evitar errores de Jinja2
        filtros = {
            'cliente': '',
            'codigo_cliente': '',
            'desde': '',
            'hasta': '',
            'estado': ''
        }
        
        return render_template(
            "cotizaciones/detalle_cotizacion.html",
            cotizacion=cotizacion,
            productos=productos,
            filtros=filtros
        )

    except Exception as e:
        flash(f'Error al cargar la cotización: {str(e)}', 'danger')
        app.logger.error(f"Error en ver_cotizacion {id}: {str(e)}")
        return redirect(url_for('gestion_cotizaciones'))

    finally:
        conexion.close()


@app.route('/admin/logs')
@superadmin_required
@login_required
def auditoria_logs():
    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT l.*, c.nombre, c.rol 
        FROM logs l
        JOIN clientes c ON l.usuario_id = c.id
        ORDER BY l.fecha DESC LIMIT 200
    ''')
    logs_data = cursor.fetchall()
    conexion.close()
    return render_template('admin/logs.html', logs=logs_data)

# Ruta para gestión de usuarios (solo superadmin)
@app.route('/admin/usuarios')
@superadmin_required
@login_required
def gestion_usuarios():
    try:
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        # Obtener todos los usuarios excepto superadmin actual, agregando el conteo de vendedores
        cursor.execute('''
            SELECT 
                u.id, 
                u.nombre, 
                u.correo, 
                u.telefono, 
                u.rol, 
                u.activo,
                u.ultima_conexion,
                u.fecha_vencimiento_suscripcion,
                (SELECT COUNT(*) FROM clientes v WHERE v.creador_id = u.id AND v.rol = 'standard') as vendedores_count
            FROM clientes u
            WHERE u.id != ? AND u.rol IN ('admin', 'superadmin', 'standard')
            ORDER BY u.rol ASC, u.nombre ASC
        ''', (session['user_id'],))
        usuarios_db = cursor.fetchall()
        conexion.close()
        
        from datetime import datetime
        ahora = datetime.now()
        usuarios = []
        for u_db in usuarios_db:
            u = dict(u_db)
            u['dias_restantes'] = None
            u['estado_color'] = 'secondary'
            
            if u['rol'] == 'admin' and u.get('fecha_vencimiento_suscripcion'):
                vence_str = str(u['fecha_vencimiento_suscripcion']).split('.')[0]
                try:
                    vence_date = datetime.strptime(vence_str, '%Y-%m-%d %H:%M:%S')
                    delta = (vence_date - ahora).days
                    u['dias_restantes'] = delta
                    if delta > 5:
                        u['estado_color'] = 'success'
                    elif delta >= 0:
                        u['estado_color'] = 'warning'
                    else:
                        u['estado_color'] = 'danger'
                except ValueError:
                    pass
            
            usuarios.append(u)

        # Crear diccionario de filtros para evitar errores en la plantilla
        filtros = {
            'cliente': '',
            'codigo_cliente': '',
            'desde': '',
            'hasta': '',
            'estado': ''
        }
        
        return render_template('admin/gestion_usuarios.html', usuarios=usuarios, filtros=filtros)

    except Exception as e:
        app.logger.error(f"Error en gestión de usuarios: {str(e)}")
        flash('Error al cargar la gestión de usuarios', 'danger')
        return redirect(url_for('admin_panel'))

@app.route('/admin/renovar_suscripcion/<int:id>', methods=['POST'])
@superadmin_required
@login_required
def renovar_suscripcion(id):
    try:
        dias = int(request.form.get('dias', 30))
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        
        cursor.execute("SELECT nombre, fecha_vencimiento_suscripcion FROM clientes WHERE id = ?", (id,))
        cliente = cursor.fetchone()
        
        if not cliente:
            flash('Administrador no encontrado', 'danger')
            return redirect(url_for('gestion_usuarios'))
            
        from datetime import datetime, timedelta
        ahora = datetime.now()
        
        # Parse existing date if any
        vence_actual = None
        if cliente['fecha_vencimiento_suscripcion']:
            vence_str = str(cliente['fecha_vencimiento_suscripcion']).split('.')[0]
            vence_actual = datetime.strptime(vence_str, '%Y-%m-%d %H:%M:%S')
            
        # Si ya tiene fecha, sumamos los días a la fecha actual o a la de vencimiento si es futura
        if vence_actual:
            base_fecha = vence_actual if vence_actual > ahora else ahora
            nueva_fecha = base_fecha + timedelta(days=dias)
        else:
            nueva_fecha = ahora + timedelta(days=dias)
            
        nueva_fecha_str = nueva_fecha.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("UPDATE clientes SET fecha_vencimiento_suscripcion = ?, activo = 1 WHERE id = ?", (nueva_fecha_str, id))
        conexion.commit()
        
        registrar_log(
            usuario_id=session['user_id'],
            accion="renovar_suscripcion",
            detalle={"admin_id": id, "dias_agregados": dias, "nueva_fecha": nueva_fecha_str}
        )
        
        flash(f'Suscripción de {cliente["nombre"]} renovada exitosamente por {dias} días.', 'success')
    except Exception as e:
        flash(f'Error al renovar suscripción: {e}', 'danger')
    finally:
        if 'conexion' in locals():
            conexion.close()
            
    return redirect(url_for('gestion_usuarios'))

@app.route('/admin/exportar_clientes_csv')
@superadmin_required
@login_required
def exportar_clientes_csv():
    try:
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        cursor.execute('''
            SELECT c.id, c.nombre, c.correo, c.telefono, c.rol, c.activo, c.fecha_vencimiento_suscripcion,
            (SELECT COUNT(*) FROM clientes v WHERE v.creador_id = c.id AND v.rol = 'standard') as vendedores
            FROM clientes c
            WHERE c.rol = 'admin'
            ORDER BY c.id ASC
        ''')
        admins = cursor.fetchall()
        conexion.close()
        
        from flask import Response
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Nombre', 'Correo', 'Telefono', 'Vendedores', 'Estado', 'Vencimiento'])
        
        for row in admins:
            activo_str = 'Activo' if row['activo'] else 'Suspendido'
            vence = str(row['fecha_vencimiento_suscripcion']).split('.')[0] if row['fecha_vencimiento_suscripcion'] else 'Sin suscripcion'
            writer.writerow([
                row['id'], row['nombre'], row['correo'], row['telefono'] or '',
                row['vendedores'], activo_str, vence
            ])
            
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=administradores_saas.csv"}
        )
    except Exception as e:
        app.logger.error(f"Error exportando CSV: {str(e)}")
        flash('Error al generar el archivo CSV', 'danger')
        return redirect(url_for('gestion_usuarios'))

# --- Modificar ruta de cotizaciones para usuarios Standard ---
@app.route('/cotizaciones/standard', endpoint='cotizaciones_standard', methods=['GET'])
@standard_required
@login_required
def standard_cotizaciones():
    # Obtener parámetros de filtro
    estado = request.args.get('estado', '')
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    conexion = get_db_connection()
    cursor = conexion.cursor()

    query = '''
        SELECT 
            c.id, 
            c.fecha, 
            c.total,
            c.estado
        FROM cotizaciones c
        WHERE c.cliente_id = ?
    '''
    params = [session['user_id']]

    # Aplicar filtros
    if estado:
        query += " AND c.estado = ?"
        params.append(estado)

    if desde:
        query += " AND DATE(c.fecha) >= ?"
        params.append(desde)

    if hasta:
        query += " AND DATE(c.fecha) <= ?"
        params.append(hasta)

    query += " ORDER BY c.fecha DESC"

    cursor.execute(query, params)
    cotizaciones = cursor.fetchall()
    conexion.close()

    return render_template('standard/standard_cotizaciones.html',
                           cotizaciones=cotizaciones,
                           filtros={'estado': estado, 'desde': desde, 'hasta': hasta})


# ----- Eliminar Cotización -----
@app.route('/cotizaciones/eliminar/<int:id>')
@login_required
def eliminar_cotizacion(id):
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Eliminar primero los productos asociados
    cursor.execute('DELETE FROM cotizacion_productos WHERE cotizacion_id=?', (id,))

    # Luego eliminar la cotización
    cursor.execute('DELETE FROM cotizaciones WHERE id=?', (id,))

    conexion.commit()
    conexion.close()
    return redirect(url_for('gestion_cotizaciones'))


# ----- Editar Cotización -----
@app.route('/cotizaciones/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_cotizacion(id):
    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    if request.method == 'POST':
        # Actualizar cliente
        cliente_id = request.form['cliente_id']
        cursor.execute("UPDATE cotizaciones SET cliente_id=? WHERE id=?",
                       (cliente_id, id))

        # Eliminar productos antiguos
        cursor.execute("DELETE FROM cotizacion_productos WHERE cotizacion_id=?", (id,))

        # Insertar nuevos productos
        items = zip(
            request.form.getlist('producto_id[]'),
            request.form.getlist('cantidad[]'),
            request.form.getlist('precio_unitario[]')
        )

        total_general = 0.0
        for producto_id, cantidad, precio_unitario in items:
            # Asegurar conversión a números
            cantidad = int(cantidad) if cantidad else 0

            precio_unitario = float(precio_unitario) if precio_unitario else 0.0
            subtotal = cantidad * precio_unitario
            total_general += subtotal

            cursor.execute('''
                INSERT INTO cotizacion_productos 
                (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?)
            ''', (id, producto_id, cantidad, precio_unitario, subtotal))

        # Actualizar total y descuentos
        try:
            descuento_porcentaje = float(request.form.get('descuento_porcentaje', 0.0) or 0.0)
        except (ValueError, TypeError):
            descuento_porcentaje = 0.0

        subtotal_bruto = total_general
        monto_descuento = round(subtotal_bruto * (descuento_porcentaje / 100.0), 2)
        total_final = max(0.0, round(subtotal_bruto - monto_descuento, 2))

        cursor.execute("UPDATE cotizaciones SET total=?, descuento_porcentaje=?, descuento_monto=?, subtotal=? WHERE id=?", 
                       (total_final, descuento_porcentaje, monto_descuento, subtotal_bruto, id))
        conexion.commit()
        conexion.close()
        return redirect(url_for('gestion_cotizaciones'))

    # Obtener datos para edición
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()

    cursor.execute("SELECT * FROM productos")
    productos = cursor.fetchall()

    # Obtener cotización actual
    cursor.execute('''
        SELECT id, cliente_id, fecha, total, descuento_porcentaje, descuento_monto, subtotal
        FROM cotizaciones
        WHERE id = ?
    ''', (id,))
    cotizacion = cursor.fetchone()

    # Obtener productos seleccionados
    cursor.execute('''
        SELECT producto_id, cantidad, precio_unitario
        FROM cotizacion_productos
        WHERE cotizacion_id = ?
    ''', (id,))
    productos_seleccionados = cursor.fetchall()

    conexion.close()

    # Crear diccionario de filtros para evitar errores en la plantilla
    filtros = {
        'cliente': '',
        'codigo_cliente': '',
        'desde': '',
        'hasta': '',
        'estado': ''
    }
    
    return render_template("cotizaciones/editar_cotizacion.html",
                           cotizacion=cotizacion,
                           clientes=clientes,
                           productos=productos,
                           productos_seleccionados=productos_seleccionados,
                           filtros=filtros)


# ----- Generar PDF de Cotización -----
@app.route('/cotizaciones/pdf/<int:id>')
@login_required
def pdf_cotizacion(id):
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Obtener datos completos del cliente y la cotización
    cursor.execute('''
        SELECT 
            c.nombre, 
            c.nit, 
            c.telefono, 
            c.correo,
            cot.id,
            cot.fecha,
            cot.total,
            cot.descuento_porcentaje,
            cot.descuento_monto,
            cot.subtotal
        FROM cotizaciones cot
        JOIN clientes c ON cot.cliente_id = c.id
        WHERE cot.id = ?
    ''', (id,))
    cotizacion_data = cursor.fetchone()

    # Obtener productos de la cotización con más detalles
    cursor.execute('''
        SELECT 
            p.empresa,
            p.codigo,
            p.descripcion,
            p.marca,
            p.tm,
            p.um,
            cp.cantidad,
            cp.precio_unitario,
            cp.subtotal
        FROM cotizacion_productos cp
        JOIN productos p ON p.id = cp.producto_id
        WHERE cp.cotizacion_id = ?
    ''', (id,))
    productos = cursor.fetchall()

    conexion.close()

    # Calcular totales
    total = cotizacion_data[6] if (cotizacion_data and cotizacion_data[6] is not None) else 0.0
    descuento_pct = cotizacion_data[7] if (cotizacion_data and len(cotizacion_data) > 7 and cotizacion_data[7] is not None) else 0.0
    descuento_monto = cotizacion_data[8] if (cotizacion_data and len(cotizacion_data) > 8 and cotizacion_data[8] is not None) else 0.0
    subtotal_bruto = cotizacion_data[9] if (cotizacion_data and len(cotizacion_data) > 9 and cotizacion_data[9] is not None and cotizacion_data[9] > 0) else sum(p[8] if len(p) > 8 and p[8] else 0.0 for p in productos)

    # Convertir total a palabras with manejo de errores
    def numero_a_palabras(numero):
        try:
            if numero is None:
                return "CERO BOLIVIANOS"

            parte_entera = int(numero)
            parte_decimal = int(round((numero - parte_entera) * 100))

            palabras_entera = num2words(parte_entera, lang='es').upper()
            palabras_decimal = num2words(parte_decimal, lang='es').upper()

            resultado = f"{palabras_entera} BOLIVIANOS"
            if parte_decimal > 0:
                resultado += f" CON {palabras_decimal} CENTAVOS"
            return resultado
        except Exception as e:
            print(f"Error convirtiendo número a palabras: {e}")
            return "CERO BOLIVIANOS"

    total_letras = numero_a_palabras(total)

    # Formatear fecha con manejo robusto
    fecha_cotizacion = datetime.now().strftime("%d/%m/%Y")  # Valor por defecto
    if cotizacion_data and cotizacion_data[5]:
        try:
            if isinstance(cotizacion_data[5], str):
                fecha_obj = datetime.strptime(cotizacion_data[5], "%Y-%m-%d %H:%M:%S")
            else:
                # Si la fecha no es string, asumimos que es timestamp
                fecha_obj = datetime.fromtimestamp(cotizacion_data[5])
            fecha_cotizacion = fecha_obj.strftime("%d/%m/%Y")
        except Exception as e:
            print(f"Error formateando fecha: {e}")
            # Mantener el valor por defecto si hay error

    # LOGO ANULADO - No cargar logo de ElectroRed
    logo_base64 = ""  # Logo anulado

    # Cargar imagen de fondo para la cotización
    fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
    fondo_base64 = ""
    app.logger.info(f"Intentando cargar imagen de fondo desde: {fondo_path}")
    
    if os.path.exists(fondo_path):
        try:
            with open(fondo_path, "rb") as image_file:
                image_data = image_file.read()
                app.logger.info(f"Imagen de fondo leída correctamente: {len(image_data)} bytes")
                fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_data).decode('utf-8')}"
                app.logger.info(f"Imagen de fondo codificada en base64: {len(fondo_base64)} caracteres")
        except Exception as e:
            app.logger.error(f"Error al procesar la imagen de fondo: {str(e)}")
    else:
        app.logger.error(f"El archivo de fondo no existe en la ruta: {fondo_path}")

    # Datos para la plantilla PDF
    # Obtener datos del usuario en sesión (nombre, teléfono, email)
    usuario = {
        'nombre': session.get('user_nombre', 'Usuario del sistema'),
        'telefono': session.get('user_telefono', None),
        'email': session.get('user_email', None)
    }
    # Si no tenemos teléfono en la sesión, intentar leerlo desde la BD
    if not usuario.get('telefono') and session.get('user_id'):
        try:
            conn_u = get_db_connection()
            cur_u = conn_u.cursor()
            cur_u.execute('SELECT nombre, telefono, correo FROM clientes WHERE id = ?', (session.get('user_id'),))
            urow = cur_u.fetchone()
            conn_u.close()
            if urow:
                usuario['nombre'] = urow[0] or usuario['nombre']
                usuario['telefono'] = urow[1] or usuario['telefono']
                usuario['email'] = urow[2] or usuario['email']
        except Exception:
            app.logger.warning('No se pudo obtener datos del usuario desde la BD para la cotización PDF')

    datos = {
        'cliente': {
            'nombre': cotizacion_data[0] if cotizacion_data and cotizacion_data[0] else "Cliente no especificado",
            'telefono': cotizacion_data[2] if cotizacion_data and cotizacion_data[2] else "S/N",
            'email': cotizacion_data[3] if cotizacion_data and cotizacion_data[3] else "S/N",
            'nit': cotizacion_data[1] if cotizacion_data and cotizacion_data[1] else "S/N",
        },
        'cotizacion': {
            'solicitud_numero': str(id) if id else "S/N",
            'fecha': fecha_cotizacion,
        },
        'productos': [{
            'codigo': p[1] if p[1] else "S/N",
            'descripcion': p[2] if p[2] else "Producto sin descripción",
            'marca': p[3] if p[3] else "S/M",
            'procedencia': "Taiwán",  # Valor predeterminado
            'cantidad': p[6] if p[6] else 0,
            'um': p[5] if p[5] else "UN",
            'precio_unitario': p[7] if p[7] else 0.0,
            'subtotal': p[8] if p[8] else 0.0
        } for p in productos],
        'subtotal': subtotal_bruto,
        'descuento': f"{descuento_pct:.2f}",
        'descuento_porcentaje': descuento_pct,
        'monto_descuento': descuento_monto,
        'total': total,
        'total_letras': total_letras,
        'usuario_sesion': session.get('user_nombre', 'Usuario del sistema'),
        'usuario': usuario,
        'logo_base64': None,  # Logo anulado por solicitud del usuario
        'fondo_base64': None  # Fondo se aplicará por página después
    }
    
    # Los fondos ahora se aplican por página después de generar el PDF

    # Renderizar plantilla HTML
    html = render_template('cotizaciones/cotizacion_pdf.html', **datos)

    # Detectar la ruta de wkhtmltopdf según el sistema operativo
    wkhtmltopdf_path = None
    if os.name == "nt":  # Windows
        # Rutas comunes en Windows
        possible_paths = [
            r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
            r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                wkhtmltopdf_path = path
                break
    else:  # Linux/Mac
        # En Linux/Mac normalmente está en el PATH
        import subprocess
        try:
            wkhtmltopdf_path = subprocess.check_output(['which', 'wkhtmltopdf']).decode().strip()
        except:
            wkhtmltopdf_path = '/usr/local/bin/wkhtmltopdf'  # Ruta común en Mac/Linux
    
    # Configuración de pdfkit con la ruta detectada
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
    options = {
        'enable-local-file-access': None,
        'encoding': 'UTF-8',
        'quiet': '',
        'margin-top': '10mm',
        'margin-right': '10mm',
        'margin-bottom': '10mm',
        'margin-left': '10mm',
    }

    try:
        app.logger.info(f"=== GENERANDO PDF COTIZACIÓN {id} ===")
        
        # Generar PDF base sin fondo
        pdf_sin_fondo = pdfkit.from_string(html, False, configuration=config, options=options)
        app.logger.info(f"PDF base generado, tamaño: {len(pdf_sin_fondo)} bytes")
        
        # Verificar cuántas páginas tiene el PDF para decidir estrategia
        temp_reader = PdfReader(io.BytesIO(pdf_sin_fondo))
        num_pages = len(temp_reader.pages)
        app.logger.info(f"PDF tiene {num_pages} páginas")
        
        if num_pages > 1:
            app.logger.info("Aplicando estrategia para múltiples páginas")
            # Para PDFs de múltiples páginas, generar versiones con diferentes márgenes
            pdf_con_fondos = generar_pdf_margenes_dinamicos(html, config, id)
        else:
            app.logger.info("Aplicando estrategia para página única")
            # Para PDF de una sola página, usar el método original
            pdf_con_fondos = aplicar_fondos_por_pagina(pdf_sin_fondo)
        
        app.logger.info(f"PDF con fondos generado, tamaño final: {len(pdf_con_fondos)} bytes")

        # Crear respuesta
        response = make_response(pdf_con_fondos)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=cotizacion_{id}.pdf'

        return response
    except OSError as e:
        app.logger.error(f"Error con wkhtmltopdf: {str(e)}")
        error_msg = """
        <h1>Error al generar PDF</h1>
        <p>No se pudo encontrar o ejecutar wkhtmltopdf. Por favor, instálelo siguiendo estos pasos:</p>
        <ol>
            <li>Descargue wkhtmltopdf desde <a href='https://wkhtmltopdf.org/downloads.html' target='_blank'>https://wkhtmltopdf.org/downloads.html</a></li>
            <li>Instálelo en su sistema</li>
            <li>Asegúrese de que la ruta al ejecutable esté correctamente configurada</li>
        </ol>
        <p>Ruta actual buscada: {}</p>
        <p>Error: {}</p>
        """.format(wkhtmltopdf_path if 'wkhtmltopdf_path' in locals() else "No configurada", str(e))
        
        return error_msg, 500
    except Exception as e:
        app.logger.error(f"Error al generar PDF: {str(e)}")
        return f"Error al generar PDF: {str(e)}", 500


# ----- Vista Previa de Cotización (HTML) -----
@app.route('/cotizaciones/vista_previa/<int:id>')
@login_required
def vista_previa_cotizacion(id):
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Obtener datos completos del cliente y la cotización
    cursor.execute('''
        SELECT 
            c.nombre, 
            c.nit, 
            c.telefono, 
            c.correo,
            cot.id,
            cot.fecha,
            cot.total,
            cot.descuento_porcentaje,
            cot.descuento_monto,
            cot.subtotal
        FROM cotizaciones cot
        JOIN clientes c ON cot.cliente_id = c.id
        WHERE cot.id = ?
    ''', (id,))
    cotizacion_data = cursor.fetchone()

    # Obtener productos de la cotización con más detalles
    cursor.execute('''
        SELECT 
            p.empresa,
            p.codigo,
            p.descripcion,
            p.marca,
            p.tm,
            p.um,
            cp.cantidad,
            cp.precio_unitario,
            cp.subtotal
        FROM cotizacion_productos cp
        JOIN productos p ON p.id = cp.producto_id
        WHERE cp.cotizacion_id = ?
    ''', (id,))
    productos = cursor.fetchall()

    conexion.close()

    # Calcular totales
    total = cotizacion_data[6] if (cotizacion_data and cotizacion_data[6] is not None) else 0.0
    descuento_pct = cotizacion_data[7] if (cotizacion_data and len(cotizacion_data) > 7 and cotizacion_data[7] is not None) else 0.0
    descuento_monto = cotizacion_data[8] if (cotizacion_data and len(cotizacion_data) > 8 and cotizacion_data[8] is not None) else 0.0
    subtotal_bruto = cotizacion_data[9] if (cotizacion_data and len(cotizacion_data) > 9 and cotizacion_data[9] is not None and cotizacion_data[9] > 0) else sum(p[8] if len(p) > 8 and p[8] else 0.0 for p in productos)

    # Convertir total a palabras con manejo de errores
    def numero_a_palabras(numero):
        try:
            if numero is None:
                return "CERO BOLIVIANOS"

            parte_entera = int(numero)
            parte_decimal = int(round((numero - parte_entera) * 100))

            palabras_entera = num2words(parte_entera, lang='es').upper()
            palabras_decimal = num2words(parte_decimal, lang='es').upper()

            resultado = f"{palabras_entera} BOLIVIANOS"
            if parte_decimal > 0:
                resultado += f" CON {palabras_decimal} CENTAVOS"
            return resultado
        except Exception as e:
            print(f"Error convirtiendo número a palabras: {e}")
            return "CERO BOLIVIANOS"

    total_letras = numero_a_palabras(total)

    # Formatear fecha con manejo robusto
    fecha_cotizacion = datetime.now().strftime("%d/%m/%Y")  # Valor por defecto
    if cotizacion_data and cotizacion_data[5]:
        try:
            if isinstance(cotizacion_data[5], str):
                fecha_obj = datetime.strptime(cotizacion_data[5], "%Y-%m-%d %H:%M:%S")
            else:
                fecha_obj = datetime.fromtimestamp(cotizacion_data[5])
            fecha_cotizacion = fecha_obj.strftime("%d/%m/%Y")
        except Exception as e:
            print(f"Error formateando fecha: {e}")
            # Mantener el valor por defecto si hay error

    # LOGO ANULADO - No cargar logo de ElectroRed
    logo_base64 = ""  # Logo anulado

    # Cargar imagen de fondo para la cotización
    fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
    fondo_base64 = ""
    print(f"Intentando cargar imagen de fondo desde: {fondo_path}")
    
    if os.path.exists(fondo_path):
        try:
            with open(fondo_path, "rb") as image_file:
                image_data = image_file.read()
                print(f"Imagen de fondo leída correctamente: {len(image_data)} bytes")
                fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_data).decode('utf-8')}"
                print(f"Imagen de fondo codificada en base64: {len(fondo_base64)} caracteres")
        except Exception as e:
            print(f"Error al procesar la imagen de fondo: {str(e)}")
    else:
        print(f"El archivo de fondo no existe en la ruta: {fondo_path}")

    # Datos para la plantilla
    usuario = {
        'nombre': session.get('user_nombre', 'Usuario del sistema'),
        'telefono': session.get('user_telefono', None),
        'email': session.get('user_email', None)
    }
    if not usuario.get('telefono') and session.get('user_id'):
        try:
            conn_u = get_db_connection()
            cur_u = conn_u.cursor()
            cur_u.execute('SELECT nombre, telefono, correo FROM clientes WHERE id = ?', (session.get('user_id'),))
            urow = cur_u.fetchone()
            conn_u.close()
            if urow:
                usuario['nombre'] = urow[0] or usuario['nombre']
                usuario['telefono'] = urow[1] or usuario['telefono']
                usuario['email'] = urow[2] or usuario['email']
        except Exception:
            print('No se pudo obtener datos del usuario desde la BD para vista previa')

    datos = {
        'cliente': {
            'nombre': cotizacion_data[0] if cotizacion_data and cotizacion_data[0] else "Cliente no especificado",
            'telefono': cotizacion_data[2] if cotizacion_data and cotizacion_data[2] else "S/N",
            'email': cotizacion_data[3] if cotizacion_data and cotizacion_data[3] else "S/N",
            'nit': cotizacion_data[1] if cotizacion_data and cotizacion_data[1] else "S/N",
        },
        'cotizacion': {
            'solicitud_numero': str(id) if id else "S/N",
            'fecha': fecha_cotizacion,
        },
        'productos': [{
            'codigo': p[1] if p[1] else "S/N",
            'descripcion': p[2] if p[2] else "Producto sin descripción",
            'marca': p[3] if p[3] else "S/M",
            'procedencia': "Taiwán",  # Valor predeterminado
            'cantidad': p[6] if p[6] else 0,
            'um': p[5] if p[5] else "UN",
            'precio_unitario': p[7] if p[7] else 0.0,
            'subtotal': p[8] if p[8] else 0.0
        } for p in productos],
        'subtotal': subtotal_bruto,
        'descuento': f"{descuento_pct:.2f}",
        'descuento_porcentaje': descuento_pct,
        'monto_descuento': descuento_monto,
        'total': total,
        'total_letras': total_letras,
        'usuario_sesion': session.get('user_nombre', 'Usuario del sistema'),
        'usuario': usuario,
        'logo_base64': None,  # Logo anulado por solicitud del usuario
        'fondo_base64': fondo_base64 if fondo_base64 else None
    }
    
    # DEBUG: Verificar si la imagen de fondo se está cargando en vista previa
    print(f"VISTA PREVIA - fondo_base64 valor: {'Si' if fondo_base64 else 'No'}")
    if fondo_base64:
        print(f"VISTA PREVIA - Longitud fondo_base64: {len(fondo_base64)}")
        print(f"VISTA PREVIA - Prefijo fondo_base64: {fondo_base64[:50]}...")

    return render_template('cotizaciones/cotizacion_pdf.html', **datos)

# --- PERFIL DE USUARIO ---
@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    try:
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row  # Esto hace que los resultados sean diccionarios
        cursor = conexion.cursor()

        if request.method == 'POST':
            nombre = request.form.get('nombre')
            telefono = request.form.get('telefono')
            correo = request.form.get('correo')

            cursor.execute('''
                UPDATE clientes 
                SET nombre = ?, telefono = ?, correo = ?
                WHERE id = ?
            ''', (nombre, telefono, correo, session['user_id']))
            conexion.commit()

            # Actualizar la sesión
            session['user_nombre'] = nombre
            session['user_email'] = correo
            flash('Perfil actualizado correctamente', 'success')
            return redirect(url_for('perfil'))

        # Obtener datos actuales del usuario
        cursor.execute('''
            SELECT nombre, correo, telefono 
            FROM clientes 
            WHERE id = ?
        ''', (session['user_id'],))
        usuario = cursor.fetchone()

        # Crear diccionario de filtros para evitar errores en la plantilla
        filtros = {
            'cliente': '',
            'codigo_cliente': '',
            'desde': '',
            'hasta': '',
            'estado': ''
        }
        
        return render_template('perfil.html', usuario=usuario, filtros=filtros)

    except Exception as e:
        app.logger.error(f"Error en perfil: {str(e)}")
        flash('Ocurrió un error al procesar tu solicitud', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        if 'conexion' in locals():
            conexion.close()

# RUTA DE PRUEBA TEMPORAL PARA VERIFICAR FONDO
@app.route('/test_fondo')
def test_fondo():
    # Cargar imagen de fondo
    fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
    fondo_base64 = ""
    
    if os.path.exists(fondo_path):
        try:
            with open(fondo_path, "rb") as image_file:
                image_data = image_file.read()
                fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_data).decode('utf-8')}"
        except Exception as e:
            print(f"Error al cargar imagen: {e}")
    
    return render_template('test_fondo.html', fondo_base64=fondo_base64)

@app.route('/suscripcion')
def suscripcion():
    # Renderizar la landing page de suscripción
    return render_template('autenticacion/suscripcion.html')

@app.route('/admin/pines', methods=['GET', 'POST'])
@login_required
def gestion_pines():
    if session.get('user_rol') != 'superadmin':
        flash('Acceso denegado. Solo el superadmin puede gestionar PINs.', 'danger')
        return redirect(url_for('index'))

    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    if request.method == 'POST':
        # Generar un nuevo PIN de 8 caracteres alfanuméricos en mayúsculas
        caracteres = string.ascii_uppercase + string.digits
        nuevo_pin = ''.join(random.choice(caracteres) for _ in range(8))
        
        try:
            cursor.execute('INSERT INTO pines_admin (pin) VALUES (?)', (nuevo_pin,))
            conexion.commit()
            flash(f'Nuevo PIN generado: {nuevo_pin}', 'success')
        except sqlite3.IntegrityError:
            flash('Error al generar el PIN (colisión). Intenta de nuevo.', 'danger')

    cursor.execute('''
        SELECT p.*, c.nombre as usado_por_nombre 
        FROM pines_admin p 
        LEFT JOIN clientes c ON p.usado_por = c.id 
        ORDER BY p.creado_en DESC
    ''')
    pines = cursor.fetchall()
    conexion.close()

    return render_template('admin/pines.html', pines=pines)

# SIEMPRE AL FINAL
if __name__ == '__main__':
    print("Rutas disponibles:")
    print(app.url_map)

    # Configuración para desarrollo
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True  # Permite manejar múltiples solicitudes
    )