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
from utils.decorators import login_required, superadmin_required, admin_required, standard_required
from utils.helpers import format_date, aplicar_fondos_por_pagina, generar_pdf_margenes_dinamicos

def _validar_acceso_cotizacion(cursor, cotizacion_id, user_id, user_rol):
    """Verifica si el usuario actual tiene permisos para acceder a una cotización específica (Anti-IDOR)"""
    if user_rol == 'superadmin':
        return True
    
    cursor.execute("""
        SELECT c.id, c.creador_id, creador.creador_id as admin_padre_id
        FROM cotizaciones c
        LEFT JOIN clientes creador ON c.creador_id = creador.id
        WHERE c.id = ?
    """, (cotizacion_id,))
    row = cursor.fetchone()
    if not row:
        return False
    
    creador_id = row['creador_id'] if hasattr(row, 'keys') else row[1]
    admin_padre_id = row['admin_padre_id'] if hasattr(row, 'keys') else row[2]
    
    # 1. Si el usuario es el creador directo
    if creador_id == user_id:
        return True
    
    # 2. Si el usuario es el Administrador de la empresa dueña del vendedor
    if admin_padre_id == user_id:
        return True
        
    # 3. Si el usuario es un Vendedor perteneciente al mismo Administrador
    cursor.execute("SELECT creador_id FROM clientes WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    mi_admin_id = u[0] if u else None
    if mi_admin_id and (creador_id == mi_admin_id or admin_padre_id == mi_admin_id):
        return True
        
    return False

def register_routes(app):
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
                admin_owner_id = session.get('creador_id') or session.get('user_id')
                cursor.execute("SELECT COUNT(*) FROM clientes WHERE (creador_id = ? OR creador_id = ?) AND rol = 'cliente'", 
                               (admin_owner_id, session['user_id']))
                total_clientes = cursor.fetchone()[0]
                cursor.execute("SELECT * FROM clientes WHERE (creador_id = ? OR creador_id = ?) AND rol = 'cliente' ORDER BY nombre LIMIT ? OFFSET ?", 
                               (admin_owner_id, session['user_id'], clientes_per_page, offset_cliente))
        clientes = cursor.fetchall()
        total_pages_clientes = (total_clientes + clientes_per_page - 1) // clientes_per_page

        # Paginación de productos para el catálogo
        per_page_param = request.args.get('per_page', '15')
        try:
            if per_page_param == 'todos':
                productos_per_page = 999999
            else:
                productos_per_page = int(per_page_param)
        except ValueError:
            productos_per_page = 15

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
        total_pages_productos = max(1, (total_productos + productos_per_page - 1) // productos_per_page) if productos_per_page < 999999 else 1

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
                'total_pages_productos': total_pages_productos,
                'total_productos': total_productos
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

        return render_template(
            'cotizaciones/cotizaciones.html',
            categorias=categorias,
            clientes=clientes,
            productos=productos,
            cotizaciones=cotizaciones,
            filtros={
                'cliente': cliente,
                'codigo_cliente': codigo_cliente,
                'desde': desde,
                'hasta': hasta
            },
            pagination={
                'page_cliente': page_cliente,
                'total_pages_clientes': total_pages_clientes,
                'page_producto': page_producto,
                'total_pages_productos': total_pages_productos,
                'page_cotizacion': page_cotizacion,
                'total_pages_cotizaciones': total_pages_cotizaciones
            },
            total_registrados=total_registrados,
            total_importados=total_importados,
            tipo_producto=tipo_producto)

    def guardar_cotizacion():
        MAX_RETRIES = 3
        RETRY_DELAY = 0.5

        # Validación inicial de claves presentes
        if not all(key in request.form for key in ['cliente_id', 'producto_id[]', 'cantidad[]', 'precio_unitario[]']):
            flash('Datos incompletos en el formulario', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

        # Validar que cliente_id sea un entero válido (no vacío)
        raw_cliente_id = request.form.get('cliente_id', '').strip()
        if not raw_cliente_id:
            flash('Debes seleccionar un cliente antes de guardar la cotización.', 'danger')
            return redirect(url_for('gestion_cotizaciones'))
        try:
            cliente_id = int(raw_cliente_id)
        except (ValueError, TypeError):
            flash('El cliente seleccionado no es válido.', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

        # Validar existencia, rol y pertenencia del cliente a la empresa
        try:
            with get_db_connection() as con_chk:
                cur_chk = con_chk.cursor()
                if session.get('user_rol') == 'superadmin':
                    cur_chk.execute("SELECT id FROM clientes WHERE id = ? AND rol = 'cliente'", (cliente_id,))
                else:
                    admin_owner_id = session.get('creador_id') or session.get('user_id')
                    cur_chk.execute('''
                        SELECT id FROM clientes 
                        WHERE id = ? AND rol = 'cliente' 
                          AND (creador_id = ? OR creador_id = ?)
                    ''', (cliente_id, admin_owner_id, session.get('user_id')))
                if not cur_chk.fetchone():
                    flash('El cliente seleccionado no existe o no pertenece a tu empresa.', 'danger')
                    return redirect(url_for('gestion_cotizaciones'))
        except Exception as ex_chk:
            app.logger.error(f"Error al validar cliente en cotización: {ex_chk}")
            return redirect(url_for('gestion_cotizaciones'))

        # Preparar datos de productos
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

                    # Iniciar transacción explícita si es SQLite (PostgreSQL maneja transacciones automáticamente)
                    if not (os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres')):
                        cursor.execute("BEGIN IMMEDIATE TRANSACTION")

                    # ── GATE FREEMIUM ─────────────────────────────────────────────
                    # Los superadmin nunca tienen restricción de prueba.
                    # Los standard heredan el estado de su admin creador.
                    # Los admin sin suscripción activa tienen 5 cotizaciones de prueba.
                    user_rol = session.get('user_rol')
                    suscripcion_activa = True   # valor seguro por defecto
                    admin_id_trial = None
                    trial_usadas = 0
                    LIMITE_TRIAL = 5

                    if user_rol != 'superadmin':
                        # Determinar el admin raíz responsable de esta cuenta
                        if user_rol == 'admin':
                            admin_id_trial = session['user_id']
                        else:
                            # standard: buscar su creador (el admin de la empresa)
                            admin_id_trial = session.get('creador_id') or session['user_id']

                        cursor.execute(
                            'SELECT fecha_vencimiento_suscripcion, cotizaciones_trial_usadas FROM clientes WHERE id = ?',
                            (admin_id_trial,)
                        )
                        admin_trial = cursor.fetchone()

                        from models import obtener_fecha_bolivia
                        now_bo = obtener_fecha_bolivia()

                        # Verificar si la suscripción está activa
                        suscripcion_activa = False
                        if admin_trial and admin_trial[0]:
                            try:
                                from datetime import datetime as _dt
                                fecha_venc = _dt.fromisoformat(str(admin_trial[0]))
                                if fecha_venc.tzinfo is None:
                                    from datetime import timezone, timedelta
                                    fecha_venc = fecha_venc.replace(tzinfo=timezone(timedelta(hours=-4)))
                                suscripcion_activa = fecha_venc > now_bo
                            except Exception:
                                suscripcion_activa = False

                        trial_usadas = (admin_trial[1] or 0) if admin_trial else 0
                        LIMITE_TRIAL = 5

                        if not suscripcion_activa and trial_usadas >= LIMITE_TRIAL:
                            # Revertir transacción abierta antes de retornar
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            return jsonify({
                                'paywall': True,
                                'trial_usadas': trial_usadas,
                                'limite': LIMITE_TRIAL,
                                'msg': f'Has usado tus {LIMITE_TRIAL} cotizaciones de prueba. Activa tu suscripción para continuar.'
                            }), 402
                    # ── FIN GATE FREEMIUM ─────────────────────────────────────────

                    # 1. Verificar stock (excepto para superadmin)
                    if session.get('user_rol') != 'superadmin':
                        for producto_id, cantidad, _, _ in productos_cotizacion:
                            cursor.execute("SELECT cantidad, stock_reservado, codigo FROM productos WHERE id=?", (producto_id,))
                            producto = cursor.fetchone()
                            
                            stock_actual = float(producto['cantidad']) if producto['cantidad'] is not None else 999.0
                            stock_reserv = float(producto['stock_reservado']) if producto['stock_reservado'] is not None else 0.0
                            stock_disponible = stock_actual - stock_reserv
                            
                            if not producto or (stock_actual != 999.0 and stock_disponible < cantidad):
                                conn.rollback()
                                codigo_p = producto['codigo'] if producto else str(producto_id)
                                flash(f"Stock insuficiente para producto {codigo_p}. Disponible: {stock_disponible}", 'danger')
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
                           (cliente_id, creador_id, fecha, total, descuento_porcentaje, descuento_monto, subtotal, estado) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')""",
                        (cliente_id, session['user_id'], fecha, total_final, descuento_porcentaje, monto_descuento, subtotal_bruto)
                    )
                    
                    # Para compatibilidad con Postgres / SQLite (algunos drivers soportan lastrowid, otros no, pero aquí se usa conn.commit después)
                    # En SQLite lastrowid funciona, en Postgres con pyscopg2 no si no usamos RETURNING
                    is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))
                    if is_postgres:
                        cursor.execute("SELECT currval(pg_get_serial_sequence('cotizaciones', 'id'))")
                        cotizacion_id = cursor.fetchone()[0]
                    else:
                        cotizacion_id = cursor.lastrowid

                    # 3. Insertar items
                    for producto_id, cantidad, precio, subtotal in productos_cotizacion:
                        cursor.execute(
                            """INSERT INTO cotizacion_productos 
                            (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                            VALUES (?, ?, ?, ?, ?)""",
                            (cotizacion_id, producto_id, cantidad, precio, subtotal)
                        )

                        # 4. Actualizar stock reservado (excepto superadmin)
                        if session.get('user_rol') != 'superadmin':
                            cursor.execute(
                                "UPDATE productos SET stock_reservado = COALESCE(stock_reservado, 0) + ? WHERE id = ?",
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

                    # ── POST-COMMIT: Incrementar contador freemium si está en prueba ──
                    if user_rol != 'superadmin' and not suscripcion_activa:
                        try:
                            with get_db_connection() as conn_trial:
                                conn_trial.cursor().execute(
                                    'UPDATE clientes SET cotizaciones_trial_usadas = cotizaciones_trial_usadas + 1 WHERE id = ?',
                                    (admin_id_trial,)
                                )
                                conn_trial.commit()
                            restantes = max(0, LIMITE_TRIAL - (trial_usadas + 1))
                            if restantes > 0:
                                flash(f'Cotización creada. Te quedan {restantes} cotización(es) de prueba gratuita.', 'success')
                            else:
                                flash('Cotización creada. ¡Has usado todas tus cotizaciones de prueba! Activa tu suscripción para continuar.', 'warning')
                        except Exception:
                            flash('Cotización creada exitosamente.', 'success')
                    else:
                        flash('Cotización creada exitosamente.', 'success')
                    # ── FIN POST-COMMIT ───────────────────────────────────────────────

                    return redirect(url_for('gestion_cotizaciones', exito=True))

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                flash(f'Error de base de datos al guardar la cotización: {str(e)}', 'danger')
                app.logger.error(f"Error en guardar_cotizacion (intento {attempt + 1}): {str(e)}")
                return redirect(url_for('gestion_cotizaciones'))

            except Exception as e:
                flash(f'Error inesperado al guardar la cotización: {str(e)}', 'danger')
                app.logger.error(f"Error inesperado en guardar_cotizacion: {str(e)}")
                return redirect(url_for('gestion_cotizaciones'))

        flash('No se pudo completar la operación después de varios intentos', 'danger')
        return redirect(url_for('gestion_cotizaciones'))

    @app.route('/cotizaciones/<int:id>')
    @login_required
    def ver_cotizacion(id):
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row  # Para acceso por nombre de columna
        cursor = conexion.cursor()
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        try:
            # Validar acceso a la cotización (Anti-IDOR)
            if not _validar_acceso_cotizacion(cursor, id, user_id, user_rol):
                flash('No tienes permisos para visualizar esta cotización.', 'danger')
                return redirect(url_for('gestion_cotizaciones'))

            # Obtener información básica de la cotización
            cursor.execute('''
                SELECT 
                    cotizaciones.id, 
                    clientes.nombre,
                    clientes.correo,
                    clientes.telefono,
                    'No disponible' as direccion,
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

    @app.route('/cotizaciones/eliminar/<int:id>')
    @login_required
    @admin_required
    def eliminar_cotizacion(id):
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        try:
            # Validar permisos (Anti-IDOR)
            if not _validar_acceso_cotizacion(cursor, id, user_id, user_rol):
                flash('No tienes permisos para eliminar esta cotización.', 'danger')
                return redirect(url_for('gestion_cotizaciones'))

            cursor.execute("SELECT estado FROM cotizaciones WHERE id = ?", (id,))
            cot_row = cursor.fetchone()
            if not cot_row:
                flash('Cotización no encontrada.', 'danger')
                return redirect(url_for('gestion_cotizaciones'))

            estado_actual = cot_row['estado'] if hasattr(cot_row, 'keys') else cot_row[0]

            # Si la cotización estaba pendiente, liberar el stock_reservado
            if estado_actual == 'pendiente':
                cursor.execute("SELECT producto_id, cantidad FROM cotizacion_productos WHERE cotizacion_id = ?", (id,))
                for item in cursor.fetchall():
                    prod_id = item['producto_id'] if hasattr(item, 'keys') else item[0]
                    cant = item['cantidad'] if hasattr(item, 'keys') else item[1]
                    cursor.execute("""
                        UPDATE productos 
                        SET stock_reservado = CASE WHEN COALESCE(stock_reservado, 0) - ? < 0 THEN 0 ELSE COALESCE(stock_reservado, 0) - ? END 
                        WHERE id = ?
                    """, (cant, cant, prod_id))

            # Eliminar productos asociados y cotización
            cursor.execute('DELETE FROM cotizacion_productos WHERE cotizacion_id=?', (id,))
            cursor.execute('DELETE FROM cotizaciones WHERE id=?', (id,))
            conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="eliminar_cotizacion",
                detalle={"cotizacion_id": id}
            )

            flash('Cotización eliminada exitosamente y stock liberado.', 'success')
        except Exception as e:
            flash(f'Error al eliminar cotización: {str(e)}', 'danger')
        finally:
            conexion.close()

        return redirect(url_for('gestion_cotizaciones'))

    @app.route('/cotizaciones/<int:id>/estado', methods=['POST'])
    @login_required
    def cambiar_estado_cotizacion(id):
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        
        try:
            data = request.get_json()
            nuevo_estado = data.get('estado')
            
            if nuevo_estado not in ['pendiente', 'aprobada', 'rechazada', 'entregado', 'anulada']:
                return jsonify({'success': False, 'message': 'Estado inválido'}), 400
                
            cursor.execute("SELECT estado, creador_id FROM cotizaciones WHERE id = ?", (id,))
            cotizacion = cursor.fetchone()
            
            if not cotizacion:
                return jsonify({'success': False, 'message': 'Cotización no encontrada'}), 404
                
            if session.get('user_rol') != 'superadmin' and not _validar_acceso_cotizacion(cursor, id, session.get('user_id'), session.get('user_rol')):
                return jsonify({'success': False, 'message': 'No tienes permiso para modificar esta cotización'}), 403

            estado_anterior = cotizacion['estado']
            
            # Solo si el estado cambia
            if estado_anterior != nuevo_estado:
                if not (os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres')):
                    cursor.execute("BEGIN IMMEDIATE TRANSACTION")
                
                # Actualizar estado en la tabla cotizaciones
                cursor.execute("UPDATE cotizaciones SET estado = ? WHERE id = ?", (nuevo_estado, id))
                
                # Obtener productos de la cotización
                cursor.execute("SELECT producto_id, cantidad FROM cotizacion_productos WHERE cotizacion_id = ?", (id,))
                productos_cotizacion = cursor.fetchall()
                
                for item in productos_cotizacion:
                    prod_id = item['producto_id']
                    cant = item['cantidad']
                    
                    # Lógica de inventario según el cambio de estado
                    if nuevo_estado == 'aprobada' and estado_anterior == 'pendiente':
                        # Pasa de pendiente a aprobada: efectúa la venta y libera reservado
                        cursor.execute(
                            """UPDATE productos SET 
                               cantidad = cantidad - ?, 
                               stock_reservado = CASE WHEN COALESCE(stock_reservado, 0) - ? < 0 THEN 0 ELSE COALESCE(stock_reservado, 0) - ? END 
                               WHERE id = ?""", 
                            (cant, cant, cant, prod_id)
                        )
                    
                    elif nuevo_estado in ['rechazada', 'anulada'] and estado_anterior == 'pendiente':
                        # Se rechaza/anula estando pendiente: liberar reservado
                        cursor.execute(
                            """UPDATE productos SET 
                               stock_reservado = CASE WHEN COALESCE(stock_reservado, 0) - ? < 0 THEN 0 ELSE COALESCE(stock_reservado, 0) - ? END 
                               WHERE id = ?""", 
                            (cant, cant, prod_id)
                        )
                    
                    elif nuevo_estado in ['anulada', 'rechazada'] and estado_anterior == 'aprobada':
                        # Se anula o rechaza una venta aprobada: Devolver (restaurar) stock real
                        cursor.execute("UPDATE productos SET cantidad = cantidad + ? WHERE id = ?", (cant, prod_id))
                    
                    elif nuevo_estado == 'pendiente' and estado_anterior == 'aprobada':
                        # Revertir venta aprobada a pendiente: Devolver a cantidad real y volver a reservar
                        cursor.execute("UPDATE productos SET cantidad = cantidad + ?, stock_reservado = COALESCE(stock_reservado, 0) + ? WHERE id = ?", (cant, cant, prod_id))
                        
                    elif nuevo_estado == 'pendiente' and estado_anterior in ['rechazada', 'anulada']:
                        # Revertir de rechazada/anulada a pendiente: Volver a reservar stock
                        cursor.execute("UPDATE productos SET stock_reservado = COALESCE(stock_reservado, 0) + ? WHERE id = ?", (cant, prod_id))
                        
                    elif nuevo_estado == 'aprobada' and estado_anterior in ['rechazada', 'anulada']:
                        # Pasa de rechazada/anulada a aprobada directamente: Descontar stock real
                        cursor.execute("UPDATE productos SET cantidad = cantidad - ? WHERE id = ?", (cant, prod_id))
                        
                registrar_log(
                    usuario_id=session['user_id'],
                    accion="cambiar_estado_cotizacion",
                    detalle={"cotizacion_id": id, "estado_anterior": estado_anterior, "nuevo_estado": nuevo_estado}
                )
                
                conexion.commit()
                
            return jsonify({'success': True, 'message': f'Estado actualizado a {nuevo_estado}'})
            
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/cotizaciones/editar/<int:id>', methods=['GET', 'POST'])
    @login_required
    def editar_cotizacion(id):
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        # Validar permisos sobre la cotización (Anti-IDOR)
        if not _validar_acceso_cotizacion(cursor, id, user_id, user_rol):
            conexion.close()
            flash('No tienes permisos para modificar esta cotización.', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

        if request.method == 'POST':
            # Actualizar cliente
            cliente_id = request.form.get('cliente_id')
            # Validar pertenencia del cliente
            if user_rol == 'superadmin':
                cursor.execute("SELECT id FROM clientes WHERE id = ? AND rol = 'cliente'", (cliente_id,))
            else:
                admin_owner_id = session.get('creador_id') or user_id
                cursor.execute("SELECT id FROM clientes WHERE id = ? AND rol = 'cliente' AND (creador_id = ? OR creador_id = ?)", (cliente_id, admin_owner_id, user_id))
            if not cursor.fetchone():
                conexion.close()
                flash('El cliente seleccionado no es válido o no pertenece a tu empresa.', 'danger')
                return redirect(url_for('gestion_cotizaciones'))

            cursor.execute("UPDATE cotizaciones SET cliente_id=? WHERE id=?", (cliente_id, id))

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

            registrar_log(
                usuario_id=user_id,
                accion="editar_cotizacion",
                detalle={"cotizacion_id": id, "total": total_final}
            )

            conexion.close()
            flash('Cotización actualizada exitosamente.', 'success')
            return redirect(url_for('gestion_cotizaciones'))

        # GET - Obtener clientes y productos acotados al tenant
        if user_rol == 'superadmin':
            cursor.execute("SELECT id, nombre, codigo_cliente FROM clientes WHERE rol = 'cliente' ORDER BY nombre")
            clientes = cursor.fetchall()
            cursor.execute("SELECT * FROM productos ORDER BY descripcion")
            productos = cursor.fetchall()
        else:
            admin_owner_id = session.get('creador_id') or user_id
            cursor.execute("SELECT id, nombre, codigo_cliente FROM clientes WHERE (creador_id = ? OR creador_id = ?) AND rol = 'cliente' ORDER BY nombre", (admin_owner_id, user_id))
            clientes = cursor.fetchall()
            cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (admin_owner_id,))
            u_row = cursor.fetchone()
            emp_nom = u_row[0] or u_row[1] or 'General' if u_row else 'General'
            cursor.execute("SELECT * FROM productos WHERE (empresa = ? OR empresa = 'General') ORDER BY descripcion", (emp_nom,))
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

    @app.route('/cotizaciones/pdf/<int:id>')
    @login_required
    def pdf_cotizacion(id):
        conexion = get_db_connection()
        cursor = conexion.cursor()
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        if not _validar_acceso_cotizacion(cursor, id, user_id, user_rol):
            conexion.close()
            flash('No tienes permisos para descargar el PDF de esta cotización.', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

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
            'fondo_base64': None,  # Fondo se aplicará por página después
            'es_pdf': True
        }
    
        # Los fondos ahora se aplican por página después de generar el PDF

        # Añadir configuración de PDF a los datos
        from models import obtener_configuracion_pdf
        datos['config_pdf'] = obtener_configuracion_pdf(session.get('user_id'))

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
            'page-size': 'Letter',
            'enable-local-file-access': None,
            'encoding': 'UTF-8',
            'quiet': '',
            'margin-top': '10mm',
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
            'no-background': ''
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

    @app.route('/cotizaciones/vista_previa/<int:id>')
    @login_required
    def vista_previa_cotizacion(id):
        conexion = get_db_connection()
        cursor = conexion.cursor()
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        if not _validar_acceso_cotizacion(cursor, id, user_id, user_rol):
            conexion.close()
            flash('No tienes permisos para visualizar esta cotización.', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

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

        # LOGO ANULADO - No cargar logo de ElectroRed
        logo_base64 = ""

        # Cargar imagen de fondo para la cotización
        fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
        fondo_base64 = ""
        if os.path.exists(fondo_path):
            try:
                with open(fondo_path, "rb") as image_file:
                    image_data = image_file.read()
                    fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_data).decode('utf-8')}"
            except Exception as e:
                print(f"Error al procesar la imagen de fondo: {str(e)}")

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
                'procedencia': "Taiwán",
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
            'logo_base64': None,
            'fondo_base64': fondo_base64 if fondo_base64 else None
        }

        # Añadir configuración de PDF a los datos
        from models import obtener_configuracion_pdf
        datos['config_pdf'] = obtener_configuracion_pdf(session.get('user_id'))

        return render_template('cotizaciones/cotizacion_pdf.html', **datos)

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

            # Aislamiento multi-tenant de productos para cotización
            user_id = session.get('user_id')
            user_rol = session.get('user_rol')
            if user_rol != 'superadmin':
                with get_db_connection() as con_t:
                    cur_t = con_t.cursor()
                    admin_id = session.get('creador_id') or user_id
                    cur_t.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (admin_id,))
                    u_t = cur_t.fetchone()
                    emp_t = u_t[0] or u_t[1] or 'General' if u_t else 'General'
                query += " AND (p.empresa = ? OR p.empresa = 'General')"
                params.append(emp_t)

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

            # Paginación dinámica (15, 30, 50, todos)
            per_page_param = request.args.get('per_page', '15').strip()
            page_producto = int(request.args.get('page_producto', request.args.get('page', 1)))
            try:
                if per_page_param == 'todos':
                    limit = 999999
                else:
                    limit = int(per_page_param)
            except ValueError:
                limit = 15

            offset = (page_producto - 1) * limit
            query_with_limit = query + f' ORDER BY p.empresa, p.codigo LIMIT {limit} OFFSET {offset}'

            # Ejecutar la consulta
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Obtener el total real sin limit
                count_sql = f"SELECT COUNT(*) FROM ({query}) AS cnt_sub"
                cursor.execute(count_sql, params)
                total_real = cursor.fetchone()[0]

                cursor.execute(query_with_limit, params)
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
                        'categoria': producto['categoria_nombre'],
                        'cantidad_total': producto['cantidad'] if session.get('user_rol') == 'superadmin' else None
                    })

                total_pages = max(1, (total_real + limit - 1) // limit) if limit < 999999 else 1

                return jsonify({
                    'success': True,
                    'productos': productos_list,
                    'total_encontrados': total_real,
                    'page_producto': page_producto,
                    'total_pages_productos': total_pages,
                    'per_page': per_page_param
                })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/buscar_clientes_cotizacion', methods=['GET'])
    @login_required
    def buscar_clientes_cotizacion():
        """Endpoint AJAX para buscar clientes sin recargar la página de cotizaciones."""
        try:
            q         = request.args.get('q', '').strip()
            page      = int(request.args.get('page', 1))
            per_page  = 8   # clientes por página en el modal AJAX

            conn   = get_db_connection()
            cursor = conn.cursor()

            like = f'%{q}%'

            if session.get('user_rol') == 'superadmin':
                base_where = "WHERE rol = 'cliente'"
                count_params = []
                if q:
                    base_where += " AND (nombre LIKE ? OR codigo_cliente LIKE ? OR nit LIKE ?)"
                    count_params = [like, like, like]
                cursor.execute(f"SELECT COUNT(*) FROM clientes {base_where}", count_params)
                total = cursor.fetchone()[0]

                query_params = count_params + [per_page, (page - 1) * per_page]
                cursor.execute(
                    f"SELECT id, nombre, codigo_cliente, nit, telefono, correo FROM clientes {base_where} ORDER BY nombre LIMIT ? OFFSET ?",
                    query_params
                )
            else:
                admin_owner_id = session.get('creador_id') or session.get('user_id')
                base_where = "WHERE rol = 'cliente' AND (creador_id = ? OR creador_id = ?)"
                count_params = [admin_owner_id, session['user_id']]
                if q:
                    base_where += " AND (nombre LIKE ? OR codigo_cliente LIKE ? OR nit LIKE ?)"
                    count_params.extend([like, like, like])
                cursor.execute(f"SELECT COUNT(*) FROM clientes {base_where}", count_params)
                total = cursor.fetchone()[0]

                query_params = count_params + [per_page, (page - 1) * per_page]
                cursor.execute(
                    f"SELECT id, nombre, codigo_cliente, nit, telefono, correo FROM clientes {base_where} ORDER BY nombre LIMIT ? OFFSET ?",
                    query_params
                )

            rows = cursor.fetchall()
            conn.close()

            total_pages = max(1, (total + per_page - 1) // per_page)

            clientes_list = [{
                'id':             r[0],
                'nombre':         r[1],
                'codigo_cliente': r[2] or '',
                'nit':            r[3] or '',
                'telefono':       r[4] or '',
                'correo':         r[5] or ''
            } for r in rows]

            return jsonify({
                'success': True,
                'clientes': clientes_list,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'per_page': per_page
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/pdf-config', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def api_pdf_config():
        conn = get_db_connection()
        cursor = conn.cursor()
        admin_id = session.get('user_id')

        if request.method == 'GET':
            try:
                cursor.execute("SELECT pdf_config FROM clientes WHERE id = ?", (admin_id,))
                res = cursor.fetchone()
                config = {}
                if res and res[0]:
                    import json
                    try:
                        config = json.loads(res[0])
                    except:
                        pass
                return jsonify({'success': True, 'config': config})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
            finally:
                conn.close()

        elif request.method == 'POST':
            try:
                data = request.json
                if not data:
                    return jsonify({'success': False, 'message': 'No data provided'}), 400

                import json
                config_json = json.dumps(data)
                cursor.execute("UPDATE clientes SET pdf_config = ? WHERE id = ?", (config_json, admin_id))
                conn.commit()
                return jsonify({'success': True, 'message': 'Configuración guardada exitosamente'})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
            finally:
                conn.close()
