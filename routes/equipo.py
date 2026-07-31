from flask import render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from db_wrapper import get_db_connection
from models import migrar_tablas_equipo, registrar_log
from utils.decorators import login_required, admin_required

def obtener_ahora_local():
    """Retorna la hora local (UTC-4) independientemente de la zona horaria del servidor en Render (UTC)"""
    return (datetime.now(timezone.utc) - timedelta(hours=4)).replace(tzinfo=None)

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
            hace_siete_dias = (obtener_ahora_local() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
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

            # 5. Solicitudes de ingreso pendientes (solo para admin/superadmin)
            solicitudes_pendientes = []
            if session.get('user_rol') in ['admin', 'superadmin']:
                cursor.execute('''
                    SELECT s.id, s.admin_id, s.empleado_id, s.estado, s.fecha_solicitud,
                           u.nombre as empleado_nombre, u.correo as empleado_correo, u.telefono as empleado_telefono
                    FROM equipo_solicitudes s
                    JOIN clientes u ON s.empleado_id = u.id
                    WHERE s.admin_id = ? AND s.estado = 'pendiente'
                    ORDER BY s.fecha_solicitud DESC
                ''', (session.get('user_id'),))
                solicitudes_pendientes = cursor.fetchall()

            return render_template(
                'equipo/equipo.html',
                mensajes_chat=mensajes_chat,
                mensajes_fijados=mensajes_fijados,
                tareas_pendientes=tareas_pendientes,
                tareas_completadas=tareas_completadas,
                usuarios_equipo=usuarios_equipo,
                notificaciones=notificaciones,
                solicitudes_pendientes=solicitudes_pendientes
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
            fecha_actual = obtener_ahora_local().strftime("%Y-%m-%d %H:%M:%S")
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
            fecha_actual = obtener_ahora_local().strftime("%Y-%m-%d %H:%M:%S")
            
            if asignados_ids:
                for u_id in asignados_ids:
                    cursor.execute('''
                        INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, descripcion, prioridad, estado, fecha_creacion, fecha_limite)
                        VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?)
                    ''', (session.get('user_id'), u_id, titulo, descripcion, prioridad, fecha_actual, fecha_limite_str))
            else:
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

            dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            ahora = obtener_ahora_local()
            nombre_dia = dias_semana[ahora.weekday()]
            fecha_completada_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
            fecha_formateada = f"{nombre_dia} {ahora.strftime('%d/%m/%Y a las %H:%M')}"

            user_id = session.get('user_id')
            user_nombre = session.get('user_nombre', 'Un usuario')

            cursor.execute('''
                UPDATE equipo_tareas 
                SET estado = 'hecho', completado_por_id = ?, fecha_completada = ?
                WHERE id = ?
            ''', (user_id, fecha_completada_str, id))

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

    # ========================================================
    # INVITACIONES POR WHATSAPP, QR Y SOLICITUDES DE INGRESO
    # ========================================================

    @app.route('/equipo/invitaciones/crear', methods=['POST'])
    @login_required
    def crear_invitacion():
        if session.get('user_rol') not in ['admin', 'superadmin']:
            return jsonify({'success': False, 'message': 'Permisos insuficientes'}), 403

        tipo_expiracion = request.form.get('tipo_expiracion', 'uso_unico')
        token = secrets.token_urlsafe(16)
        
        # Calcular fecha de expiración y usos según opción
        usos_restantes = 1 if tipo_expiracion == 'uso_unico' else -1
        fecha_expiracion = None
        now = obtener_ahora_local()

        if tipo_expiracion == '1_dia':
            fecha_expiracion = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif tipo_expiracion == '1_semana':
            fecha_expiracion = (now + timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif tipo_expiracion == '1_mes':
            fecha_expiracion = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        elif tipo_expiracion == '3_meses':
            fecha_expiracion = (now + timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        elif tipo_expiracion == '6_meses':
            fecha_expiracion = (now + timedelta(days=180)).strftime("%Y-%m-%d %H:%M:%S")

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            cursor.execute('''
                INSERT INTO equipo_invitaciones (admin_id, token, tipo_expiracion, usos_restantes, fecha_expiracion)
                VALUES (?, ?, ?, ?, ?)
            ''', (session.get('user_id'), token, tipo_expiracion, usos_restantes, fecha_expiracion))
            conexion.commit()

            link_invitacion = url_for('unirse_equipo', token=token, _external=True)
            return jsonify({
                'success': True,
                'token': token,
                'link_invitacion': link_invitacion
            })
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/unirse-equipo', methods=['GET'])
    def unirse_equipo():
        token = request.args.get('token', '').strip()
        if not token:
            return render_template('equipo/unirse_equipo.html', invitacion_valida=False)

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute('''
                SELECT i.id, i.admin_id, i.token, i.tipo_expiracion, i.usos_restantes, i.fecha_expiracion,
                       u.nombre as admin_nombre
                FROM equipo_invitaciones i
                JOIN clientes u ON i.admin_id = u.id
                WHERE i.token = ?
            ''', (token,))
            inv = cursor.fetchone()

            if not inv:
                return render_template('equipo/unirse_equipo.html', invitacion_valida=False)

            # Si el usuario actual ya está conectado o envió solicitud
            user_id = session.get('user_id')
            esta_vinculado = False
            solicitud_existente = None

            if user_id:
                cursor.execute("SELECT creador_id FROM clientes WHERE id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row and user_row['creador_id'] == inv['admin_id']:
                    esta_vinculado = True

                cursor.execute('''
                    SELECT id, estado, fecha_solicitud 
                    FROM equipo_solicitudes 
                    WHERE admin_id = ? AND empleado_id = ? AND estado = 'pendiente'
                ''', (inv['admin_id'], user_id))
                solicitud_existente = cursor.fetchone()

            # Validar expiración (solo si el usuario no ha enviado ya la solicitud)
            if not esta_vinculado and not solicitud_existente:
                if inv['tipo_expiracion'] == 'uso_unico' and inv['usos_restantes'] <= 0:
                    return render_template('equipo/unirse_equipo.html', invitacion_valida=False)

                if inv['fecha_expiracion']:
                    fecha_exp = datetime.strptime(inv['fecha_expiracion'], "%Y-%m-%d %H:%M:%S")
                    if obtener_ahora_local() > fecha_exp:
                        return render_template('equipo/unirse_equipo.html', invitacion_valida=False)

            return render_template(
                'equipo/unirse_equipo.html',
                invitacion_valida=True,
                token=token,
                admin_nombre=inv['admin_nombre'],
                admin_id=inv['admin_id'],
                esta_vinculado=esta_vinculado,
                solicitud_existente=solicitud_existente
            )
        finally:
            conexion.close()

    @app.route('/equipo/solicitudes/enviar', methods=['POST'])
    @login_required
    def enviar_solicitud_ingreso():
        token = request.form.get('token', '').strip()
        user_id = session.get('user_id')

        if not token or not user_id:
            flash('Solicitud inválida o sesión no iniciada', 'danger')
            return redirect(url_for('gestion_cotizaciones'))

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT id, admin_id, tipo_expiracion, usos_restantes FROM equipo_invitaciones WHERE token = ?", (token,))
            inv = cursor.fetchone()

            if not inv:
                flash('La invitación no es válida', 'danger')
                return redirect(url_for('gestion_cotizaciones'))

            admin_id = inv['admin_id']

            # Verificar si ya existe solicitud pendiente
            cursor.execute("SELECT id FROM equipo_solicitudes WHERE admin_id = ? AND empleado_id = ? AND estado = 'pendiente'", (admin_id, user_id))
            if cursor.fetchone():
                flash('Ya tienes una solicitud pendiente enviada a este Administrador', 'info')
                return redirect(url_for('unirse_equipo', token=token))

            # Registrar solicitud (sin fecha de expiración)
            fecha_actual = obtener_ahora_local().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO equipo_solicitudes (admin_id, empleado_id, estado, fecha_solicitud)
                VALUES (?, ?, 'pendiente', ?)
            ''', (admin_id, user_id, fecha_actual))

            # Si es uso único, decrementar usos
            if inv['tipo_expiracion'] == 'uso_unico':
                cursor.execute("UPDATE equipo_invitaciones SET usos_restantes = usos_restantes - 1 WHERE id = ?", (inv['id'],))

            # Notificar al Administrador
            user_nombre = session.get('user_nombre', 'Un usuario')
            msg_notif = f"El empleado {user_nombre} solicitó unirse a tu equipo."
            cursor.execute('''
                INSERT INTO equipo_notificaciones (usuario_id, mensaje, tipo, fecha)
                VALUES (?, ?, 'solicitud_ingreso', ?)
            ''', (admin_id, msg_notif, fecha_actual))

            conexion.commit()
            flash('¡Solicitud de ingreso enviada exitosamente al Administrador!', 'success')
            return redirect(url_for('unirse_equipo', token=token))
        except Exception as e:
            conexion.rollback()
            flash(f'Error al enviar solicitud: {str(e)}', 'danger')
            return redirect(url_for('gestion_cotizaciones'))
        finally:
            conexion.close()

    @app.route('/equipo/solicitudes/<int:id>/aprobar', methods=['POST'])
    @login_required
    def aprobar_solicitud_ingreso(id):
        if session.get('user_rol') not in ['admin', 'superadmin']:
            return jsonify({'success': False, 'message': 'Permisos insuficientes'}), 403

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT id, admin_id, empleado_id, estado FROM equipo_solicitudes WHERE id = ?", (id,))
            sol = cursor.fetchone()
            if not sol:
                return jsonify({'success': False, 'message': 'Solicitud no encontrada'}), 404

            if sol['admin_id'] != session.get('user_id') and session.get('user_rol') != 'superadmin':
                return jsonify({'success': False, 'message': 'No tienes permiso para aprobar esta solicitud'}), 403

            # Aprobar solicitud y vincular empleado al Admin
            cursor.execute("UPDATE equipo_solicitudes SET estado = 'aprobada' WHERE id = ?", (id,))
            cursor.execute("UPDATE clientes SET creador_id = ? WHERE id = ?", (sol['admin_id'], sol['empleado_id']))

            registrar_log(
                usuario_id=session.get('user_id'),
                accion="aprobar_solicitud_equipo",
                detalle={"solicitud_id": id, "empleado_id": sol['empleado_id']}
            )

            conexion.commit()
            return jsonify({'success': True, 'message': 'Solicitud aprobada. Empleado vinculado al equipo.'})
        except Exception as e:
            conexion.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conexion.close()

    @app.route('/equipo/solicitudes/<int:id>/rechazar', methods=['POST'])
    @login_required
    def rechazar_solicitud_ingreso(id):
        if session.get('user_rol') not in ['admin', 'superadmin']:
            return jsonify({'success': False, 'message': 'Permisos insuficientes'}), 403

        conexion = get_db_connection()
        cursor = conexion.cursor()
        try:
            cursor.execute("UPDATE equipo_solicitudes SET estado = 'rechazada' WHERE id = ?", (id,))
            conexion.commit()
            return jsonify({'success': True, 'message': 'Solicitud rechazada.'})
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
