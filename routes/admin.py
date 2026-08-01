from flask import Flask, flash, render_template, request, redirect, session, url_for, make_response, jsonify, send_from_directory
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
        if session.get('user_rol') == 'superadmin':
            # Cargar datos exclusivos para superadmin
            return render_template('admin/superadmin_dashboard.html',
                                 funciones_exclusivas=True)
        elif session.get('user_rol') == 'admin':
            return render_template('admin/admin_dashboard.html')  # Panel normal
        else:
            return redirect(url_for('standard_dashboard'))

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

    @app.route('/admin/usuarios/<int:id>', methods=['DELETE'])
    @superadmin_required
    @login_required
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
    @superadmin_required
    @login_required
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
            now_bo = obtener_fecha_bolivia()
            fecha_str = now_bo.strftime('%Y-%m-%d %H:%M:%S')
        
            try:
                cursor.execute('INSERT INTO pines_admin (pin, creado_en) VALUES (?, ?)', (nuevo_pin, fecha_str))
                conexion.commit()
                flash(f'Nuevo PIN generado: {nuevo_pin}', 'success')
            except sqlite3.IntegrityError:
                flash('Error al generar el PIN (colisión). Intenta de nuevo.', 'danger')
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
    
    @app.route('/admin/respaldos')
    @superadmin_required
    @login_required
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
    @superadmin_required
    @login_required
    def crear_respaldo_route():
        try:
            filename, _ = crear_backup()
            registrar_log(session.get('user_id'), "CREAR_RESPALDO", f"Respaldo creado: {filename}")
            flash(f"Respaldo '{filename}' creado exitosamente.", 'success')
        except Exception as e:
            flash(f"Error al generar el respaldo: {str(e)}", 'danger')
        return redirect(url_for('gestion_respaldos'))

    @app.route('/admin/respaldos/descargar/<filename>')
    @superadmin_required
    @login_required
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
    @superadmin_required
    @login_required
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
    @superadmin_required
    @login_required
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
    
    
