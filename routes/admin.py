from flask import Flask, flash, render_template, request, redirect, session, url_for, make_response, jsonify, send_from_directory, Response
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
import secrets
import re
from db_wrapper import get_db_connection
from sqlite3 import connect  # Esta es la importación que faltaba
from markupsafe import Markup
from threading import Lock
from contextlib import contextmanager
from models import (
    crear_tablas, registrar_log, migrar_clientes_existentes, migrar_productos_categorias,
    migrar_columnas_nuevas_clientes,
    guardar_importacion_pdf, obtener_importaciones_pdf, obtener_importacion_por_id, registrar_productos_seleccionados,
    eliminar_importacion_pdf, obtener_fecha_bolivia
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
from utils.backup import crear_backup, listar_backups, eliminar_backup, restaurar_backup, get_backup_dir

def register_routes(app):
    @app.route('/admin')
    @login_required
    def admin_panel():
        return redirect(url_for('dashboard'))

    @app.route('/admin/logs')
    @login_required
    @superadmin_required
    def auditoria_logs():
        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            # Parámetros de filtrado
            filtro_accion = request.args.get('accion', '').strip()
            filtro_usuario_id = request.args.get('usuario_id', '').strip()
            filtro_desde = request.args.get('desde', '').strip()
            filtro_hasta = request.args.get('hasta', '').strip()
            filtro_buscar = request.args.get('buscar', '').strip()
            limite_val = request.args.get('limite', '200').strip()
            try:
                limite = min(max(int(limite_val), 50), 1000)
            except ValueError:
                limite = 200

            # Construcción dinámica de la consulta
            condiciones = []
            parametros = []

            if filtro_accion:
                condiciones.append("l.accion = ?")
                parametros.append(filtro_accion)

            if filtro_usuario_id:
                if filtro_usuario_id == 'anonimo':
                    condiciones.append("l.usuario_id IS NULL")
                elif filtro_usuario_id.isdigit():
                    condiciones.append("l.usuario_id = ?")
                    parametros.append(int(filtro_usuario_id))

            if filtro_desde:
                condiciones.append("l.fecha >= ?")
                parametros.append(f"{filtro_desde} 00:00:00")

            if filtro_hasta:
                condiciones.append("l.fecha <= ?")
                parametros.append(f"{filtro_hasta} 23:59:59")

            if filtro_buscar:
                condiciones.append("(l.detalle LIKE ? OR l.accion LIKE ? OR c.nombre LIKE ? OR c.correo LIKE ?)")
                search_term = f"%{filtro_buscar}%"
                parametros.extend([search_term, search_term, search_term, search_term])

            where_clause = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

            query = f'''
                SELECT l.id, l.usuario_id, l.accion, l.detalle, l.fecha,
                       COALESCE(c.nombre, 'Sistema / Anónimo') as nombre,
                       COALESCE(c.rol, 'sistema') as rol,
                       c.correo as usuario_correo
                FROM logs l
                LEFT JOIN clientes c ON l.usuario_id = c.id
                {where_clause}
                ORDER BY l.fecha DESC LIMIT ?
            '''
            parametros.append(limite)
            cursor.execute(query, tuple(parametros))
            logs_data = [dict(r) for r in cursor.fetchall()]

            # Obtener catálogo de acciones distintas para el dropdown de filtro
            cursor.execute("SELECT DISTINCT accion FROM logs ORDER BY accion ASC")
            acciones_disponibles = [r['accion'] for r in cursor.fetchall() if r['accion']]

            # Obtener catálogo de usuarios para el dropdown de filtro
            cursor.execute("SELECT id, nombre, rol, correo FROM clientes WHERE rol IN ('superadmin', 'admin', 'standard') ORDER BY nombre ASC")
            usuarios_disponibles = [dict(r) for r in cursor.fetchall()]

            conexion.close()

            filtros_aplicados = {
                'accion': filtro_accion,
                'usuario_id': filtro_usuario_id,
                'desde': filtro_desde,
                'hasta': filtro_hasta,
                'buscar': filtro_buscar,
                'limite': limite
            }

            return render_template(
                'admin/logs.html',
                logs=logs_data,
                acciones=acciones_disponibles,
                usuarios=usuarios_disponibles,
                filtros=filtros_aplicados,
                total_encontrados=len(logs_data)
            )
        except Exception as e:
            app.logger.error(f"Error en auditoria_logs: {str(e)}")
            flash('Error al consultar los registros de auditoría', 'danger')
            return redirect(url_for('admin_panel'))

    @app.route('/admin/logs/exportar-csv')
    @login_required
    @superadmin_required
    def exportar_logs_csv():
        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            filtro_accion = request.args.get('accion', '').strip()
            filtro_usuario_id = request.args.get('usuario_id', '').strip()
            filtro_desde = request.args.get('desde', '').strip()
            filtro_hasta = request.args.get('hasta', '').strip()
            filtro_buscar = request.args.get('buscar', '').strip()

            condiciones = []
            parametros = []

            if filtro_accion:
                condiciones.append("l.accion = ?")
                parametros.append(filtro_accion)

            if filtro_usuario_id:
                if filtro_usuario_id == 'anonimo':
                    condiciones.append("l.usuario_id IS NULL")
                elif filtro_usuario_id.isdigit():
                    condiciones.append("l.usuario_id = ?")
                    parametros.append(int(filtro_usuario_id))

            if filtro_desde:
                condiciones.append("l.fecha >= ?")
                parametros.append(f"{filtro_desde} 00:00:00")

            if filtro_hasta:
                condiciones.append("l.fecha <= ?")
                parametros.append(f"{filtro_hasta} 23:59:59")

            if filtro_buscar:
                condiciones.append("(l.detalle LIKE ? OR l.accion LIKE ? OR c.nombre LIKE ? OR c.correo LIKE ?)")
                search_term = f"%{filtro_buscar}%"
                parametros.extend([search_term, search_term, search_term, search_term])

            where_clause = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

            query = f'''
                SELECT l.id, l.fecha, l.usuario_id,
                       COALESCE(c.nombre, 'Sistema / Anónimo') as nombre,
                       COALESCE(c.correo, '-') as correo,
                       COALESCE(c.rol, 'sistema') as rol,
                       l.accion, l.detalle
                FROM logs l
                LEFT JOIN clientes c ON l.usuario_id = c.id
                {where_clause}
                ORDER BY l.fecha DESC LIMIT 5000
            '''
            cursor.execute(query, tuple(parametros))
            logs = cursor.fetchall()
            conexion.close()

            from flask import Response
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Fecha y Hora', 'Usuario ID', 'Nombre', 'Correo', 'Rol', 'Accion', 'Detalle'])

            for r in logs:
                writer.writerow([
                    r['id'], r['fecha'], r['usuario_id'] or 'N/A',
                    r['nombre'], r['correo'], r['rol'],
                    r['accion'], r['detalle'] or ''
                ])

            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment;filename=auditoria_global_{obtener_fecha_bolivia().strftime('%Y%m%d_%H%M%S')}.csv"}
            )
        except Exception as e:
            app.logger.error(f"Error exportando logs CSV: {str(e)}")
            flash('Error al exportar logs de auditoría', 'danger')
            return redirect(url_for('auditoria_logs'))

    @app.route('/admin/usuarios')
    @login_required
    @superadmin_required
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

    @app.route('/admin/historial-usuarios')
    @login_required
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
                    COALESCE(u.nombre, 'Sistema / Anónimo') as usuario_nombre,
                    l.accion,
                    l.detalle,
                    l.fecha,
                    COALESCE(u.correo, '-') as usuario_email,
                    COALESCE(u.rol, 'sistema') as usuario_rol
                FROM logs l
                LEFT JOIN clientes u ON l.usuario_id = u.id
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
    @login_required
    @admin_required
    def crear_usuario():
        try:
            # Obtener datos (compatible con form-data y JSON)
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form

            nombre = (data.get('nombre') or '').strip()
            correo = (data.get('correo') or '').strip().lower()
            telefono = (data.get('telefono') or '').strip()
            rol = data.get('rol')
            contrasena = data.get('contrasena') or ''

            # Validaciones básicas
            if not all([nombre, correo, rol, contrasena]):
                return jsonify({'error': 'Faltan campos requeridos'}), 400

            if len(contrasena) < 6:
                return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

            if rol not in ['admin', 'standard']:
                return jsonify({'error': 'Rol no válido'}), 400

            # Validar que solo superadmin pueda crear otros admins
            if rol == 'admin' and session.get('user_rol') != 'superadmin':
                return jsonify({'error': 'Solo superadmin puede crear usuarios admin'}), 403

            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            # Verificar correo único (insensible a mayúsculas)
            cursor.execute("SELECT id FROM clientes WHERE LOWER(correo) = ?", (correo,))
            if cursor.fetchone():
                conexion.close()
                return jsonify({'error': 'El correo ya está registrado'}), 400

            # Obtener empresa_nombre del creador para herencia
            empresa_creador = None
            cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (session['user_id'],))
            u_creador = cursor.fetchone()
            if u_creador:
                empresa_creador = u_creador['empresa_nombre'] or u_creador['nombre'] or 'General'

            # Crear hash de la contraseña
            contrasena_hash = generate_password_hash(contrasena)

            # Insertar nuevo usuario
            cursor.execute('''
                INSERT INTO clientes (nombre, correo, telefono, rol, contrasena, creador_id, activo, empresa_nombre)
                VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)
            ''', (nombre, correo, telefono, rol, contrasena_hash, session['user_id'], empresa_creador))

            conexion.commit()
            conexion.close()

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
    @login_required
    @admin_required
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

            # Verificar si el usuario existe y validar permisos de acceso
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute("SELECT id, rol, creador_id FROM clientes WHERE id = ?", (id,))
            target_user = cursor.fetchone()
            if not target_user:
                conexion.close()
                return jsonify({'error': 'Usuario no encontrado'}), 404

            caller_rol = session.get('user_rol')
            caller_id = session.get('user_id')

            # Control estricto de privilegios (Evitar IDOR y escalada de privilegios)
            if caller_rol != 'superadmin':
                # Un admin normal no puede modificar a un superadmin ni a otro admin
                if target_user['rol'] in ['superadmin', 'admin'] and target_user['id'] != caller_id:
                    conexion.close()
                    return jsonify({'error': 'No tienes permisos para modificar este usuario'}), 403
                # Un admin normal solo puede editar sus propios subordinados (vendedores)
                if target_user['rol'] == 'standard' and target_user['creador_id'] != caller_id:
                    conexion.close()
                    return jsonify({'error': 'No tienes permisos para modificar usuarios de otra organización'}), 403
                # Un admin normal no puede elevar a nadie a superadmin o admin
                if rol != 'standard' and target_user['id'] != caller_id:
                    conexion.close()
                    return jsonify({'error': 'No puedes asignar privilegios de administrador'}), 403

            # Verificar si el correo ya existe para otro usuario
            cursor.execute("SELECT id FROM clientes WHERE LOWER(correo) = ? AND id != ?", (correo.lower(), id))
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
                ''', (nombre, correo.lower(), telefono, rol, contrasena_hash, id))
            else:
                cursor.execute('''
                    UPDATE clientes SET 
                        nombre = ?,
                        correo = ?,
                        telefono = ?,
                        rol = ?
                    WHERE id = ?
                ''', (nombre, correo.lower(), telefono, rol, id))

            conexion.commit()
            conexion.close()

            return jsonify({'success': True}), 200

        except Exception as e:
            app.logger.error(f"Error al actualizar usuario {id}: {str(e)}")
            return jsonify({'error': 'Error del servidor'}), 500

    @app.route('/admin/usuarios/<int:id>/rol', methods=['PUT'])
    @login_required
    @superadmin_required
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
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            
            cursor.execute("SELECT id, rol, nombre FROM clientes WHERE id = ?", (id,))
            target_user = cursor.fetchone()
            if not target_user:
                conexion.close()
                return jsonify({'error': 'Usuario no encontrado'}), 404

            rol_anterior = target_user['rol']
            cursor.execute("UPDATE clientes SET rol = ? WHERE id = ?", (nuevo_rol, id))
            conexion.commit()

            registrar_log(
                usuario_id=session['user_id'],
                accion="cambio_rol_usuario",
                detalle={
                    "usuario_afectado": id,
                    "nombre": target_user['nombre'],
                    "rol_anterior": rol_anterior,
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
        caller_rol = session.get('user_rol')
        caller_id = session.get('user_id')

        if caller_rol not in ['admin', 'superadmin']:
            return jsonify({'error': 'No autorizado'}), 403

        # Validar que no sea el usuario actual
        if id == caller_id:
            return jsonify({'error': 'No puedes cambiar tu propio estado'}), 400

        data = request.json or {}
        activo = data.get('activo')

        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            # Validar permisos sobre el usuario objetivo
            cursor.execute("SELECT id, rol, creador_id FROM clientes WHERE id = ?", (id,))
            target_user = cursor.fetchone()
            if not target_user:
                conexion.close()
                return jsonify({'error': 'Usuario no encontrado'}), 404

            if caller_rol != 'superadmin':
                if target_user['rol'] in ['superadmin', 'admin']:
                    conexion.close()
                    return jsonify({'error': 'No puedes suspender a otro administrador'}), 403
                if target_user['creador_id'] != caller_id:
                    conexion.close()
                    return jsonify({'error': 'No puedes suspender usuarios de otra empresa'}), 403

            cursor.execute("UPDATE clientes SET activo = ? WHERE id = ?", (activo, id))
            conexion.commit()

            registrar_log(
                usuario_id=caller_id,
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

    @app.route('/admin/usuarios/<int:id>', methods=['DELETE'])
    @login_required
    @superadmin_required
    def eliminar_usuario_completo(id):
        if id == session.get('user_id'):
            return jsonify({'error': 'No puedes eliminar tu propia cuenta'}), 400

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            # 1. Obtener usuario
            cursor.execute("SELECT id, nombre, correo, rol FROM clientes WHERE id = ?", (id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'Usuario no encontrado'}), 404

            user_nombre = user[1] if isinstance(user, (tuple, list)) else user['nombre']
            user_correo = user[2] if isinstance(user, (tuple, list)) else user['correo']

            # 2. Si es admin, desvincular o limpiar sus empleados asociados
            cursor.execute("UPDATE clientes SET creador_id = NULL WHERE creador_id = ?", (id,))

            # 3. Eliminar cotizaciones y sus productos
            cursor.execute('''
                DELETE FROM cotizacion_productos WHERE cotizacion_id IN (
                    SELECT id FROM cotizaciones WHERE cliente_id = ? OR creador_id = ?
                )
            ''', (id, id))
            cursor.execute("DELETE FROM cotizaciones WHERE cliente_id = ? OR creador_id = ?", (id, id))

            # 4. Eliminar tareas, chat, notificaciones y solicitudes
            cursor.execute("DELETE FROM equipo_tareas WHERE creador_id = ? OR asignado_a = ? OR completado_por_id = ?", (id, id, id))
            cursor.execute("DELETE FROM equipo_chat WHERE usuario_id = ?", (id,))
            cursor.execute("DELETE FROM equipo_notificaciones WHERE usuario_id = ?", (id,))
            cursor.execute("DELETE FROM equipo_solicitudes WHERE admin_id = ? OR empleado_id = ?", (id, id))
            cursor.execute("DELETE FROM equipo_invitaciones WHERE admin_id = ?", (id,))

            # 4.5 Eliminar importaciones pdf
            cursor.execute('''
                DELETE FROM items_importados_temp WHERE importacion_id IN (
                    SELECT id FROM importaciones_pdf WHERE usuario_id = ?
                )
            ''', (id,))
            cursor.execute("DELETE FROM importaciones_pdf WHERE usuario_id = ?", (id,))

            # 5. Eliminar logs, config pdf y des-asociar pines/renovaciones
            cursor.execute("DELETE FROM logs WHERE usuario_id = ?", (id,))
            cursor.execute("DELETE FROM configuracion_pdf WHERE usuario_id = ?", (id,))
            cursor.execute("UPDATE pines_admin SET usado = FALSE, usado_por = NULL WHERE usado_por = ?", (id,))
            cursor.execute("DELETE FROM historial_renovaciones WHERE admin_id = ? OR superadmin_id = ?", (id, id))

            # 6. Eliminar registro del cliente/usuario
            cursor.execute("DELETE FROM clientes WHERE id = ?", (id,))

            registrar_log(
                usuario_id=session.get('user_id'),
                accion="eliminar_usuario_completo",
                detalle={"usuario_eliminado_id": id, "nombre": user_nombre, "correo": user_correo}
            )

            conexion.commit()
            return jsonify({'success': True, 'message': f'Usuario {user_nombre} ({user_correo}) y toda su información fueron eliminados permanentemente.'})
        except Exception as e:
            conexion.rollback()
            return jsonify({'error': f'Error al eliminar usuario: {str(e)}'}), 500
        finally:
            conexion.close()

    @app.route('/admin/renovar_suscripcion/<int:id>', methods=['POST'])
    @login_required
    @superadmin_required
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
        
            # Guardar en el historial de renovaciones
            notas = request.form.get('notas', '')
            cursor.execute("""
                INSERT INTO historial_renovaciones (admin_id, dias_agregados, superadmin_id, notas)
                VALUES (?, ?, ?, ?)
            """, (id, dias, session['user_id'], notas))
        
            conexion.commit()
        
            registrar_log(
                usuario_id=session['user_id'],
                accion="renovar_suscripcion",
                detalle={"admin_id": id, "dias_agregados": dias, "nueva_fecha": nueva_fecha_str, "notas": notas}
            )
        
            flash(f'Suscripción de {cliente["nombre"]} renovada exitosamente por {dias} días.', 'success')
        except Exception as e:
            flash(f'Error al renovar suscripción: {e}', 'danger')
        finally:
            if 'conexion' in locals():
                conexion.close()
            
        return redirect(url_for('gestion_usuarios'))

    @app.route('/admin/usuarios/<int:id>/historial_renovaciones', methods=['GET'])
    @login_required
    @superadmin_required
    def obtener_historial_renovaciones(id):
        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
        
            cursor.execute("""
                SELECT h.id, h.dias_agregados, h.fecha_renovacion, h.notas, s.nombre as superadmin_nombre
                FROM historial_renovaciones h
                LEFT JOIN clientes s ON h.superadmin_id = s.id
                WHERE h.admin_id = ?
                ORDER BY h.fecha_renovacion DESC
            """, (id,))
        
            historial = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'historial': historial})
        except Exception as e:
            app.logger.error(f"Error al obtener historial de {id}: {str(e)}")
            return jsonify({'error': 'Error al cargar historial'}), 500
        finally:
            if 'conexion' in locals():
                conexion.close()

    @app.route('/admin/exportar_clientes_csv')
    @login_required
    @superadmin_required
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

    @app.route('/admin/pines', methods=['GET', 'POST'])
    @login_required
    @superadmin_required
    def gestion_pines():
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        if request.method == 'POST':
            # Generar un nuevo PIN criptográficamente seguro de 8 caracteres alfanuméricos sin ambigüedades
            caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            nuevo_pin = ''.join(secrets.choice(caracteres) for _ in range(8))
            now_bo = obtener_fecha_bolivia()
            fecha_str = now_bo.strftime('%Y-%m-%d %H:%M:%S')
        
            try:
                cursor.execute('INSERT INTO pines_admin (pin, creado_en) VALUES (?, ?)', (nuevo_pin, fecha_str))
                conexion.commit()

                registrar_log(
                    usuario_id=session.get('user_id'),
                    accion="generar_pin_admin",
                    detalle={"pin": nuevo_pin, "fecha": fecha_str}
                )

                flash(f'Nuevo PIN generado: {nuevo_pin}', 'success')
            except Exception as ex_pin:
                conexion.rollback()
                flash('Error al generar el PIN (posible colisión). Intenta nuevamente.', 'danger')
            finally:
                conexion.close()
            return redirect(url_for('gestion_pines'))

        cursor.execute('''
            SELECT p.*, c.nombre as usado_por_nombre 
            FROM pines_admin p 
            LEFT JOIN clientes c ON p.usado_por = c.id 
            ORDER BY p.creado_en DESC
        ''')
        rows = cursor.fetchall()
        pines = []
        from datetime import timezone, timedelta
        tz_bolivia = timezone(timedelta(hours=-4))
        for row in rows:
            p = dict(row)
            creado = p.get('creado_en')
            if isinstance(creado, datetime):
                if creado.tzinfo is not None:
                    creado = creado.astimezone(tz_bolivia)
                p['creado_en'] = creado.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(creado, str) and creado:
                try:
                    dt = datetime.fromisoformat(creado.replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(tz_bolivia)
                    p['creado_en'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            pines.append(p)
        conexion.close()

        return render_template('admin/pines.html', pines=pines)

    @app.route('/admin/pines/eliminar/<int:pin_id>', methods=['POST'])
    @login_required
    @superadmin_required
    def eliminar_pin(pin_id):
        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            
            cursor.execute("SELECT id, pin, usado, usado_por FROM pines_admin WHERE id = ?", (pin_id,))
            pin_row = cursor.fetchone()

            cursor.execute("DELETE FROM pines_admin WHERE id = ?", (pin_id,))
            conexion.commit()

            if pin_row:
                registrar_log(
                    usuario_id=session.get('user_id'),
                    accion="eliminar_pin_admin",
                    detalle={"pin_id": pin_id, "pin": pin_row['pin'], "usado": bool(pin_row['usado'])}
                )

            conexion.close()
            flash('PIN eliminado exitosamente del registro.', 'success')
        except Exception as e:
            flash(f'Error al eliminar el PIN: {str(e)}', 'danger')
        return redirect(url_for('gestion_pines'))


    @app.route('/admin/usuarios/<int:id>', methods=['GET'])
    @login_required
    @admin_required
    def obtener_usuario(id):
        try:
            caller_rol = session.get('user_rol')
            caller_id = session.get('user_id')

            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute("SELECT id, nombre, correo, telefono, rol, creador_id FROM clientes WHERE id = ?", (id,))
            usuario = cursor.fetchone()
            conexion.close()
    
            if not usuario:
                return jsonify({'error': 'Usuario no encontrado'}), 404

            # Anti-IDOR: Superadmin puede ver a todos, un admin normal solo puede ver sus propios datos o los de sus subordinados
            if caller_rol != 'superadmin':
                if usuario['id'] != caller_id and usuario['creador_id'] != caller_id:
                    return jsonify({'error': 'No tienes permisos para consultar este usuario'}), 403
    
            return jsonify({
                'id': usuario['id'],
                'nombre': usuario['nombre'],
                'correo': usuario['correo'],
                'telefono': usuario['telefono'],
                'rol': usuario['rol']
            })
    
        except Exception as e:
            app.logger.error(f"Error al obtener usuario {id}: {str(e)}")
            return jsonify({'error': 'Error del servidor'}), 500

    @app.route('/empresa/respaldo/exportar')
    @app.route('/admin/empresa/respaldo')
    @login_required
    @admin_required
    def exportar_respaldo_empresa():
        try:
            from utils.backup import generar_respaldo_empresa_excel
            user_id = session.get('user_id')
            user_rol = session.get('user_rol')

            target_admin_id = user_id
            if user_rol == 'superadmin' and request.args.get('admin_id'):
                try:
                    target_admin_id = int(request.args.get('admin_id'))
                except ValueError:
                    target_admin_id = user_id
            elif user_rol == 'standard':
                target_admin_id = session.get('creador_id') or user_id

            excel_bytes, filename = generar_respaldo_empresa_excel(target_admin_id)
            if not excel_bytes:
                flash('No se encontraron datos para exportar de esta empresa.', 'danger')
                return redirect(url_for('dashboard'))

            registrar_log(
                usuario_id=user_id,
                accion="exportar_respaldo_empresa_excel",
                detalle={"target_admin_id": target_admin_id, "filename": filename}
            )

            response = Response(
                excel_bytes,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
            return response
        except Exception as e:
            app.logger.error(f"Error exportando respaldo Excel de empresa: {str(e)}")
            flash(f"Error al generar la copia de seguridad en Excel: {str(e)}", 'danger')
            return redirect(url_for('dashboard'))

    @app.route('/admin/respaldos')
    @login_required
    @superadmin_required
    def gestion_respaldos():
        try:
            backups = listar_backups()
            total_bytes = sum(b['size_bytes'] for b in backups)
            total_mb = round(total_bytes / (1024 * 1024), 2)
            return render_template('admin/respaldos.html', backups=backups, total_mb=total_mb)
        except Exception as e:
            flash(f"Error al cargar el panel de respaldos: {str(e)}", 'danger')
            return redirect(url_for('admin_panel'))

    @app.route('/admin/respaldos/crear', methods=['POST'])
    @login_required
    @superadmin_required
    def crear_respaldo_route():
        try:
            filename, _ = crear_backup()
            registrar_log(session.get('user_id'), "CREAR_RESPALDO", f"Respaldo creado: {filename}")
            flash(f"Respaldo '{filename}' creado exitosamente.", 'success')
        except Exception as e:
            flash(f"Error al generar el respaldo: {str(e)}", 'danger')
        return redirect(url_for('gestion_respaldos'))

    @app.route('/admin/respaldos/descargar/<filename>')
    @login_required
    @superadmin_required
    def descargar_respaldo(filename):
        try:
            safe_filename = os.path.basename(filename)
            backup_dir = get_backup_dir()
            registrar_log(session.get('user_id'), "DESCARGAR_RESPALDO", f"Respaldo descargado: {safe_filename}")
            return send_from_directory(backup_dir, safe_filename, as_attachment=True)
        except Exception as e:
            flash(f"Error al descargar el respaldo: {str(e)}", 'danger')
            return redirect(url_for('gestion_respaldos'))

    @app.route('/admin/respaldos/eliminar/<filename>', methods=['POST'])
    @login_required
    @superadmin_required
    def eliminar_respaldo_route(filename):
        try:
            safe_filename = os.path.basename(filename)
            eliminar_backup(safe_filename)
            registrar_log(session.get('user_id'), "ELIMINAR_RESPALDO", f"Respaldo eliminado: {safe_filename}")
            flash(f"Respaldo '{safe_filename}' eliminado correctamente.", 'success')
        except Exception as e:
            flash(f"Error al eliminar el respaldo: {str(e)}", 'danger')
        return redirect(url_for('gestion_respaldos'))

    @app.route('/admin/respaldos/restaurar/<filename>', methods=['POST'])
    @login_required
    @superadmin_required
    def restaurar_respaldo_route(filename):
        try:
            safe_filename = os.path.basename(filename)
            restaurar_backup(safe_filename)
            registrar_log(session.get('user_id'), "RESTAURAR_RESPALDO", f"Sistema restaurado a la versión: {safe_filename}")
            flash(f"Sistema restaurado exitosamente a la versión '{safe_filename}'. Se generó un respaldo automático previo.", 'warning')
        except Exception as e:
            flash(f"Error al restaurar el respaldo: {str(e)}", 'danger')
        return redirect(url_for('gestion_respaldos'))

    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    
    
