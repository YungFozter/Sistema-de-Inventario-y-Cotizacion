import pytest
import os
import sqlite3
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
from models import crear_tablas

TEST_DB = 'TEST/test_db.sqlite3'

def get_test_db_connection():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn

@pytest.fixture(scope='session')
def app():
    # Setup test environment
    os.environ['TESTING_DB'] = TEST_DB
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    
    # Initialize tables in the test db
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    conexion = get_test_db_connection()
    # Patch models so it creates tables in the right DB context since models might call get_db_connection inside
    from models import crear_tablas, migrar_clientes_existentes, migrar_productos_categorias, migrar_columnas_nuevas_clientes
    with patch('models.get_db_connection', side_effect=get_test_db_connection):
        crear_tablas()
        migrar_clientes_existentes()
        migrar_productos_categorias()
        migrar_columnas_nuevas_clientes()
    conexion.close()
    
    yield flask_app
    
    # Cleanup
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except PermissionError:
            pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def superadmin_user(app):
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    from werkzeug.security import generate_password_hash
    hashed = generate_password_hash('password123')
    cursor.execute("INSERT INTO clientes (nombre, correo, contrasena, rol, activo) VALUES ('Super Test', 'super@test.com', ?, 'superadmin', 1)", (hashed,))
    conexion.commit()
    user_id = cursor.lastrowid
    conexion.close()
    
    # Cleanup after test
    yield {'id': user_id, 'email': 'super@test.com', 'rol': 'superadmin', 'password': 'password123'}
    
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = ?", (user_id,))
    conexion.commit()
    conexion.close()

@pytest.fixture
def admin_user(app):
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    from werkzeug.security import generate_password_hash
    hashed = generate_password_hash('password123')
    cursor.execute("INSERT INTO clientes (nombre, correo, contrasena, rol, activo) VALUES ('Admin Test', 'admin@test.com', ?, 'admin', 1)", (hashed,))
    conexion.commit()
    user_id = cursor.lastrowid
    conexion.close()
    
    yield {'id': user_id, 'email': 'admin@test.com', 'rol': 'admin', 'password': 'password123'}
    
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = ?", (user_id,))
    conexion.commit()
    conexion.close()

@pytest.fixture
def standard_user(app):
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    from werkzeug.security import generate_password_hash
    hashed = generate_password_hash('password123')
    cursor.execute("INSERT INTO clientes (nombre, correo, contrasena, rol, activo) VALUES ('Standard Test', 'standard@test.com', ?, 'standard', 1)", (hashed,))
    conexion.commit()
    user_id = cursor.lastrowid
    conexion.close()
    
    yield {'id': user_id, 'email': 'standard@test.com', 'rol': 'standard', 'password': 'password123'}
    
    conexion = get_test_db_connection()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = ?", (user_id,))
    conexion.commit()
    conexion.close()
