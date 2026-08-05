from flask import flash, render_template, request, redirect, session, url_for, make_response, jsonify
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
import re as _re_global
from db_wrapper import get_db_connection
from sqlite3 import connect
from markupsafe import Markup
from threading import Lock
from contextlib import contextmanager
from models import (
    crear_tablas, registrar_log, migrar_clientes_existentes, migrar_productos_categorias,
    migrar_columnas_nuevas_clientes,
    guardar_importacion_pdf, obtener_importaciones_pdf, obtener_importacion_por_id,
    registrar_productos_seleccionados, eliminar_importacion_pdf
)
from utils.pdf_extractor import PDFProductExtractor
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import uuid


from authlib.integrations.flask_client import OAuth
oauth = OAuth()
google = None

def register_routes(app):

    global google
    oauth.init_app(app)
    google = oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        access_token_url='https://accounts.google.com/o/oauth2/token',
        access_token_params=None,
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        authorize_params=None,
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )


    # ─── Helpers de validación reutilizables ──────────────────────────────────
    def _validar_telefono_bo(telefono: str):
        """Devuelve el número normalizado (sin prefijo) o None si es inválido."""
        if not telefono:
            return ''  # opcional
        tel = _re_global.sub(r'\D', '', telefono)
        if tel.startswith('591') and len(tel) > 9:
            tel = tel[3:]
        if _re_global.match(r'^[67]\d{7}$', tel) or _re_global.match(r'^[234]\d{6}$', tel):
            return tel
        return None

    def _insertar_cliente(cursor, conexion, nombre, empresa_nombre, correo, telefono,
                          contrasena_hash, rol='admin', auth_provider='local'):
        """Inserta un nuevo cliente y devuelve su ID."""
        is_postgres = bool(
            not os.environ.get('TESTING_DB') and
            os.environ.get('DATABASE_URL') and
            os.environ.get('DATABASE_URL').startswith('postgres')
        )

        query = '''
            INSERT INTO clientes
                (nombre, empresa_nombre, correo, telefono, contrasena, rol,
                 fecha_vencimiento_suscripcion, cotizaciones_trial_usadas, auth_provider)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?)
        '''
        if is_postgres:
            query = query.replace('?', '%s') + ' RETURNING id'
            cursor.execute(query, (nombre, empresa_nombre, correo, telefono, contrasena_hash, rol, auth_provider))
            row = cursor.fetchone()
            nuevo_id = row[0] if row else None
        else:
            cursor.execute(query, (nombre, empresa_nombre, correo, telefono, contrasena_hash, rol, auth_provider))
            nuevo_id = cursor.lastrowid

        if not nuevo_id:
            cursor.execute('SELECT id FROM clientes WHERE correo = ?', (correo,))
            row = cursor.fetchone()
            if row:
                nuevo_id = row[0]
        return nuevo_id

    # ─── /registro  GET ───────────────────────────────────────────────────────
    @app.route('/registro', methods=['GET'])
    def registro():
        return render_template('autenticacion/registro.html')


    # ─── /registro POST (Manual, sin verificación) ───────────────────────────
    @app.route('/registro', methods=['POST'])
    def registro_post():
        data = request.form
        nombre = data.get('nombre', '').strip()
        empresa = data.get('empresa_nombre', '').strip()
        correo = data.get('correo', '').strip().lower()
        contrasena = data.get('contrasena', '')
        telefono = data.get('telefono', '').strip()

        if not nombre or not correo or not contrasena:
            flash('Faltan campos obligatorios.', 'danger')
            return redirect(url_for('registro'))

        try:
            con = get_db_connection()
            cur = con.cursor()
            cur.execute('SELECT id FROM clientes WHERE correo = ?', (correo,))
            if cur.fetchone():
                flash('Este correo ya está registrado.', 'warning')
                con.close()
                return redirect(url_for('registro'))
            
            # Formatear telefono (opcional)
            tel_ok = _validar_telefono_bo(telefono)
            telefono_norm = f'+591{tel_ok}' if tel_ok else ''

            nuevo_id = _insertar_cliente(
                cur, con,
                nombre=nombre,
                empresa_nombre=empresa,
                correo=correo,
                telefono=telefono_norm,
                contrasena_hash=generate_password_hash(contrasena),
                rol='admin',
                auth_provider='local'
            )
            con.commit()
            con.close()
            
            flash('¡Bienvenido a COTIZAPro! Tu cuenta ha sido creada.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('registro'))

    # ─── Google OAuth 2.0 ────────────────────────────────────────────────────
    @app.route('/auth/google')
    def auth_google():
        redirect_uri = url_for('auth_google_callback', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route('/auth/google/callback')
    def auth_google_callback():
        try:
            token = google.authorize_access_token()
            user_info = token.get('userinfo')
            if not user_info:
                # Authlib fetch user info
                user_info = google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
            
            correo = user_info.get('email', '').lower()
            nombre = user_info.get('name', '')
            
            if not correo:
                flash('No se pudo obtener el correo de Google.', 'danger')
                return redirect(url_for('login'))
                
            con = get_db_connection()
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            
            # Buscar si el usuario ya existe
            cur.execute('SELECT * FROM clientes WHERE correo = ?', (correo,))
            cliente = cur.fetchone()
            
            if cliente:
                # Login
                session.clear()
                session['usuario_id'] = cliente['id']
                session['nombre'] = cliente['nombre']
                session['rol'] = cliente['rol']
                session['empresa_nombre'] = cliente['empresa_nombre']
                
                # Actualizar auth_provider si era local
                if cliente['auth_provider'] != 'google':
                    cur.execute('UPDATE clientes SET auth_provider = ? WHERE id = ?', ('google', cliente['id']))
                
                registrar_log(cliente['id'], 'login_google', {'ip': request.remote_addr})
                con.commit()
                con.close()
                flash('Has iniciado sesión correctamente con Google.', 'success')
                return redirect(url_for('dashboard'))
            else:
                # Registrar
                nuevo_id = _insertar_cliente(
                    cur, con,
                    nombre=nombre,
                    empresa_nombre='',
                    correo=correo,
                    telefono='',
                    contrasena_hash='',
                    rol='admin',
                    auth_provider='google'
                )
                con.commit()
                
                session.clear()
                session['usuario_id'] = nuevo_id
                session['nombre'] = nombre
                session['rol'] = 'admin'
                session['empresa_nombre'] = ''
                
                registrar_log(nuevo_id, 'registro_google', {'ip': request.remote_addr})
                con.close()
                flash('¡Bienvenido! Tu cuenta ha sido creada con Google.', 'success')
                return redirect(url_for('dashboard'))
                
        except Exception as e:
            print(f'[GOOGLE AUTH ERROR] {e}')
            flash('Error al iniciar sesión con Google.', 'danger')
            return redirect(url_for('login'))

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

                # Generar nuevo token único de sesión activa
                session_token = uuid.uuid4().hex

                # Actualizar ultima_conexion y session_token de forma segura
                try:
                    cursor.execute('UPDATE clientes SET ultima_conexion = CURRENT_TIMESTAMP, session_token = ? WHERE id = ?', (session_token, cliente['id']))
                    conexion.commit()
                except Exception as err_tok:
                    print(f"[WARN] Error actualizando session_token: {err_tok}")
                    conexion.rollback()
                    try:
                        cursor.execute('UPDATE clientes SET ultima_conexion = CURRENT_TIMESTAMP WHERE id = ?', (cliente['id'],))
                        conexion.commit()
                    except Exception:
                        pass
                finally:
                    conexion.close()

                # Guardar sesión
                session['user_id'] = cliente['id']
                session['user_nombre'] = cliente['nombre']
                session['user_rol'] = rol
                session['user_email'] = cliente['correo']
                session['session_token'] = session_token

                # Datos freemium (solo relevantes para rol admin)
                if rol == 'admin':
                    from models import obtener_fecha_bolivia
                    from datetime import timedelta as _td
                    trial_usadas = cliente['cotizaciones_trial_usadas'] if 'cotizaciones_trial_usadas' in cliente.keys() else 0
                    fecha_venc = cliente['fecha_vencimiento_suscripcion']
                    suscripcion_activa = False
                    if fecha_venc:
                        try:
                            venc_dt = datetime.strptime(str(fecha_venc).split('.')[0], '%Y-%m-%d %H:%M:%S')
                            suscripcion_activa = venc_dt > datetime.now()
                        except Exception:
                            pass
                    session['trial_usadas'] = trial_usadas or 0
                    session['trial_activo'] = (not suscripcion_activa)
                    session['creador_id'] = None
                elif rol == 'standard':
                    session['creador_id'] = cliente['creador_id']
                    session['trial_activo'] = False
                else:
                    session['trial_activo'] = False

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
        user_id = session.get('user_id')
        if user_id:
            try:
                conexion = get_db_connection()
                cursor = conexion.cursor()
                cursor.execute("UPDATE clientes SET session_token = NULL WHERE id = ?", (user_id,))
                conexion.commit()
                conexion.close()
            except Exception:
                pass
        session.clear()
        flash('Has cerrado sesión exitosamente', 'info')
        return redirect('/login')

    @app.route('/suscripcion/activar-pin', methods=['POST'])
    def activar_pin_paywall():
        """Endpoint JSON para activar un PIN de suscripción desde el modal paywall."""
        if 'user_id' not in session or session.get('user_rol') != 'admin':
            return jsonify({'ok': False, 'msg': 'No autorizado'}), 403

        data = request.get_json(silent=True) or {}
        pin_ingresado = (data.get('pin') or '').strip()

        if not pin_ingresado:
            return jsonify({'ok': False, 'msg': 'Debes ingresar un PIN'}), 400

        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()

            cursor.execute('SELECT id, usado FROM pines_admin WHERE pin = ?', (pin_ingresado,))
            pin_rec = cursor.fetchone()

            if not pin_rec or pin_rec[1]:
                conexion.close()
                return jsonify({'ok': False, 'msg': 'PIN inválido o ya utilizado'}), 400

            from models import obtener_fecha_bolivia
            from datetime import timedelta
            now_bo = obtener_fecha_bolivia()
            fecha_venc = (now_bo + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute(
                'UPDATE clientes SET fecha_vencimiento_suscripcion = ? WHERE id = ?',
                (fecha_venc, session['user_id'])
            )
            cursor.execute(
                'UPDATE pines_admin SET usado = 1, usado_por = ? WHERE id = ?',
                (session['user_id'], pin_rec[0])
            )
            conexion.commit()
            conexion.close()

            # Actualizar session: suscripción activa
            session['trial_activo'] = False
            return jsonify({'ok': True, 'msg': 'Suscripción activada por 30 días'}), 200

        except Exception as e:
            return jsonify({'ok': False, 'msg': f'Error: {str(e)}'}), 500

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

    @app.route('/suscripcion')
    def suscripcion():
        # Renderizar la landing page de suscripción
        return render_template('autenticacion/suscripcion.html')

