from flask import render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
from datetime import datetime, timedelta
from db_wrapper import get_db_connection
from models import migrar_tablas_equipo, registrar_log
from utils.decorators import login_required, admin_required

def register_routes(app):

    @app.route('/equipo', methods=['GET'])
    @login_required
    def vista_equipo():
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        
        try:
            is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))
            
            # 1. Purgar/filtrar chat de más de 7 días (Limpieza automática)
            hace_siete_dias = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Obtener mensajes del chat <= 7 días
            cursor.execute('''
                SELECT c.id, c.usuario_id, u.nombre as usuario_nombre, u.rol as usuario_rol,
                       c.mensaje, c.es_fijado, c.fecha
                FROM equipo_chat c
                JOIN clientes u ON c.usuario_id = u.id
                WHERE c.fecha >= ? OR c.es_fijado = TRUE
                ORDER BY c.fecha ASC
            ''', (hace_siete_dias,))
            mensajes_chat = cursor.fetchall()
            
            # Mensajes fijados (Anuncios)
            cursor.execute('''
                SELECT c.id, c.usuario_id, u.nombre as usuario_nombre, c.mensaje, c.fecha
                FROM equipo_chat c
                JOIN clientes u ON c.usuario_id = u.id
                WHERE c.es_fijado = TRUE
                ORDER BY c.fecha DESC
            ''')
            mensajes_fijados = cursor.fetchall()

            # 2. Obtener Tareas Pendientes y Completadas
            cursor.execute('''
                SELECT t.id, t.creador_id, uc.nombre as creador_nombre,
                       t.asignado_a, ua.nombre as asignado_nombre,
                       t.titulo, t.descripcion, t.prioridad, t.estado,
                       t.fecha_creacion, t.fecha_completada, t.fecha_limite,
                       t.completado_por_id, ucomp.nombre as completado_por_nombre
                FROM equipo_tareas t
                JOIN clientes uc ON t.creador_id = uc.id
                LEFT JOIN clientes ua ON t.asignado_a = ua.id
                LEFT JOIN clientes ucomp ON t.completado_por_id = ucomp.id
                ORDER BY t.estado DESC, t.id DESC
            ''')
            todas_tareas = cursor.fetchall()
            
            tareas_pendientes = [t for t in todas_tareas if t['estado'] == 'pendiente']
            tareas_completadas = [t for t in todas_tareas if t['estado'] == 'hecho']

            # 3. Lista de usuarios activos para asignación de tareas
            cursor.execute("SELECT id, nombre, rol FROM clientes WHERE activo = TRUE ORDER BY nombre ASC")
            usuarios_equipo = cursor.fetchall()
            
            # 4. Notificaciones del usuario actual
            cursor.execute('''
                SELECT id, mensaje, tipo, leido, fecha
                FROM equipo_notificaciones
                WHERE usuario_id = ?
                ORDER BY fecha DESC LIMIT 15
            ''', (session.get('user_id'),))
            notificaciones = cursor.fetchall()

            return render_template(
                'equipo/equipo.html',
                mensajes_chat=mensajes_chat,
                mensajes_fijados=mensajes_fijados,
                tareas_pendientes=tareas_pendientes,
                tareas_completadas=tareas_completadas,
                usuarios_equipo=usuarios_equipo,
                notificaciones=notificaciones
            )
        except Exception as e:
            flash(f"Error al cargar el módulo de equipo: {str(e)}", "danger")
            return redirect(url_for('gestion_cotizaciones'))
        finally:
            conexion.close()

    @app.route('/equipo/chat', methods=['POST'])
    @login_required
    def enviar_mensaje_chat():
        mensaje = request.form.get('mensaje', '').strip()
        if not mensaje:
            return jsonify({'success': False, 'message': 'El mensaje no puede estar vacío'}), 400

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO equipo_chat (usuario_id, mensaje, fecha) VALUES (?, ?, ?)",
                (session.get('user_id'), mensaje, fecha_actual)
            )
            conexion.commit()
            return jsonify({'success': True})
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/equipo/chat/<int:id>/fijar', methods=['POST'])
    @login_required
    def fijar_mensaje_chat(id):
        if session.get('user_rol') not in ['admin', 'superadmin']:
            return jsonify({'success': False, 'message': 'Permisos insuficientes'}), 403

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT es_fijado FROM equipo_chat WHERE id = ?", (id,))
            msg = cursor.fetchone()
            if not msg:
                return jsonify({'success': False, 'message': 'Mensaje no encontrado'}), 404
            
            nuevo_estado = not bool(msg['es_fijado'])
            cursor.execute("UPDATE equipo_chat SET es_fijado = ? WHERE id = ?", (nuevo_estado, id))
            conexion.commit()
            return jsonify({'success': True, 'es_fijado': nuevo_estado})
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/equipo/tareas', methods=['POST'])
    @login_required
    def crear_tarea():
        if session.get('user_rol') not in ['admin', 'superadmin']:
            flash('Solo administradores pueden asignar tareas', 'danger')
            return redirect(url_for('vista_equipo'))

        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        prioridad = request.form.get('prioridad', 'media')
        asignados_raw = request.form.getlist('asignado_a[]') or request.form.getlist('asignado_a')
        
        fecha_limite_val = request.form.get('fecha_limite', '').strip()
        hora_limite_val = request.form.get('hora_limite', '').strip()

        if not titulo:
            flash('El título de la tarea es obligatorio', 'danger')
            return redirect(url_for('vista_equipo'))

        # Procesar Fecha y Hora límite
        fecha_limite_str = None
        if fecha_limite_val:
            if not hora_limite_val:
                hora_limite_val = "00:00:00"
            elif len(hora_limite_val) == 5:
                hora_limite_val += ":00"
            fecha_limite_str = f"{fecha_limite_val} {hora_limite_val}"

        # Procesar asignados
        asignados_ids = []
        for val in asignados_raw:
            if val and val.isdigit():
                asignados_ids.append(int(val))

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if asignados_ids:
                # Crear una tarea para cada empleado seleccionado
                for u_id in asignados_ids:
                    cursor.execute('''
                        INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, descripcion, prioridad, estado, fecha_creacion, fecha_limite)
                        VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?)
                    ''', (session.get('user_id'), u_id, titulo, descripcion, prioridad, fecha_actual, fecha_limite_str))
            else:
                # Tarea para todo el equipo (asignado_a = None)
                cursor.execute('''
                    INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, descripcion, prioridad, estado, fecha_creacion, fecha_limite)
                    VALUES (?, NULL, ?, ?, ?, 'pendiente', ?, ?)
                ''', (session.get('user_id'), titulo, descripcion, prioridad, fecha_actual, fecha_limite_str))

            conexion.commit()
            flash('Tarea(s) asignada(s) exitosamente', 'success')
        except Exception as e:
            conexion.rollback()
            flash(f'Error al crear tarea: {str(e)}', 'danger')
        finally:
            conexion.close()

        return redirect(url_for('vista_equipo'))

    @app.route('/equipo/tareas/<int:id>/completar', methods=['POST'])
    @login_required
    def completar_tarea(id):
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT id, titulo, creador_id, estado FROM equipo_tareas WHERE id = ?", (id,))
            tarea = cursor.fetchone()
            if not tarea:
                return jsonify({'success': False, 'message': 'Tarea no encontrada'}), 404

            if tarea['estado'] == 'hecho':
                return jsonify({'success': False, 'message': 'La tarea ya estaba completada'}), 400

            # Fecha y Hora exacta en formato amigable
            dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            ahora = datetime.now()
            nombre_dia = dias_semana[ahora.weekday()]
            fecha_completada_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
            fecha_formateada = f"{nombre_dia} {ahora.strftime('%d/%m/%Y a las %H:%M')}"

            user_id = session.get('user_id')
            user_nombre = session.get('user_nombre', 'Un usuario')

            # Actualizar tarea
            cursor.execute('''
                UPDATE equipo_tareas 
                SET estado = 'hecho', completado_por_id = ?, fecha_completada = ?
                WHERE id = ?
            ''', (user_id, fecha_completada_str, id))

            # Notificar al creador/administradores
            msg_notif = f"El usuario {user_nombre} completó la tarea '{tarea['titulo']}' el {fecha_formateada}."
            cursor.execute('''
                INSERT INTO equipo_notificaciones (usuario_id, mensaje, tipo, fecha)
                VALUES (?, ?, 'tarea_completada', ?)
            ''', (tarea['creador_id'], msg_notif, fecha_completada_str))

            registrar_log(
                usuario_id=user_id,
                accion="completar_tarea",
                detalle={"tarea_id": id, "titulo": tarea['titulo'], "fecha_completada": fecha_formateada}
            )

            conexion.commit()
            return jsonify({'success': True, 'fecha_formateada': fecha_formateada, 'completado_por': user_nombre})
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/equipo/tareas/<int:id>/eliminar', methods=['POST'])
    @login_required
    def eliminar_tarea(id):
        if session.get('user_rol') not in ['admin', 'superadmin']:
            return jsonify({'success': False, 'message': 'Permisos insuficientes'}), 403

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            cursor.execute("DELETE FROM equipo_tareas WHERE id = ?", (id,))
            conexion.commit()
            return jsonify({'success': True})
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/equipo/notificaciones', methods=['GET'])
    @login_required
    def obtener_notificaciones():
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute('''
                SELECT id, mensaje, tipo, leido, fecha
                FROM equipo_notificaciones
                WHERE usuario_id = ? AND leido = FALSE
                ORDER BY fecha DESC LIMIT 10
            ''', (session.get('user_id'),))
            notifs = [dict(r) for r in cursor.fetchall()]
            return jsonify({'success': True, 'notificaciones': notifs})
        finally:
            conexion.close()

    @app.route('/equipo/notificaciones/marcar-leidas', methods=['POST'])
    @login_required
    def marcar_notificaciones_leidas():
        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            cursor.execute("UPDATE equipo_notificaciones SET leido = TRUE WHERE usuario_id = ?", (session.get('user_id'),))
            conexion.commit()
            return jsonify({'success': True})
        finally:
            conexion.close()
