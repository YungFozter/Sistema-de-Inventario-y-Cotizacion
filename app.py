from flask import Flask
import os
import sqlite3
from datetime import datetime
from db_wrapper import get_db_connection
from models import crear_tablas

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

import builtins
builtins.app = app

# Inicializar Base de Datos
def inicializar_base_datos():
    if not os.path.exists('database'):
        os.makedirs('database')
    
    conexion = get_db_connection()
    crear_tablas()
    conexion.close()

inicializar_base_datos()

# Context Processor
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Register Routes
from routes.auth import register_routes as init_auth
from routes.admin import register_routes as init_admin
from routes.clientes import register_routes as init_clientes
from routes.productos import register_routes as init_productos
from routes.cotizaciones import register_routes as init_cotizaciones
from routes.core import register_routes as init_core

init_auth(app)
init_admin(app)
init_clientes(app)
init_productos(app)
init_cotizaciones(app)
init_core(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)