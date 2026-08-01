from flask import Flask
import os
import sqlite3
from datetime import datetime
from db_wrapper import get_db_connection
from models import crear_tablas, migrar_columnas_nuevas_clientes, migrar_esquema_productos, migrar_tablas_equipo

import logging
for _log_name in ['pdfminer', 'pdfminer.pdfinterp', 'pdfminer.pdfpage', 'pdfminer.converter', 'pdfminer.layout', 'PyPDF2', 'pypdf', 'pdfplumber']:
    logging.getLogger(_log_name).setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

import builtins
builtins.app = app

# Inicializar Base de Datos
def inicializar_base_datos():
    try:
        if not os.path.exists('database'):
            os.makedirs('database')
        
        crear_tablas()
        migrar_columnas_nuevas_clientes()
        migrar_esquema_productos()
        migrar_tablas_equipo()
    except Exception as e:
        print(f"[WARN] No se pudo inicializar/migrar la base de datos en inicio: {e}")

inicializar_base_datos()

# Context Processor
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Control de Sesión Única Activa en Tiempo Real
from flask import session, request, redirect, url_for, flash

@app.before_request
def verificar_sesion_unica():
    if request.endpoint and (request.endpoint.startswith('static') or request.endpoint in ('login', 'registro', 'logout')):
        return

    user_id = session.get('user_id')
    token_sesion = session.get('session_token')

    if user_id and token_sesion:
        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()
            cursor.execute("SELECT session_token FROM clientes WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            conexion.close()

            if row:
                db_token = row[0] if isinstance(row, (tuple, list)) else row['session_token']
                if db_token and db_token != token_sesion:
                    session.clear()
                    # Detectar si es una petición AJAX/API para retornar JSON en vez de redirect
                    is_ajax = (
                        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                        or 'application/json' in request.headers.get('Accept', '')
                        or (request.path.startswith('/api/'))
                    )
                    if is_ajax:
                        from flask import jsonify
                        return jsonify({'success': False, 'error': 'sesion_invalidada', 'redirect': '/login'}), 401
                    flash('Tu sesión ha sido cerrada automáticamente porque tu cuenta inició sesión en otro dispositivo o navegador.', 'warning')
                    return redirect(url_for('login'))
        except Exception:
            pass

# Register Routes
from routes.auth import register_routes as init_auth
from routes.admin import register_routes as init_admin
from routes.clientes import register_routes as init_clientes
from routes.productos import register_routes as init_productos
from routes.cotizaciones import register_routes as init_cotizaciones
from routes.core import register_routes as init_core
from routes.mi_pdf import register_mi_pdf_routes as init_mi_pdf
from routes.equipo import register_routes as init_equipo

init_auth(app)
init_admin(app)
init_clientes(app)
init_productos(app)
init_cotizaciones(app)
init_core(app)
init_mi_pdf(app)
init_equipo(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)