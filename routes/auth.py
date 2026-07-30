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
import uuid

def register_routes(app):
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

