import os
import sys
import unittest
import json
import sqlite3

# Añadir directorio raíz al path de Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Configurar DB de prueba aislada ANTES de cargar la app
TEST_DB_PATH = 'database/test_ventas_security.db'
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass
os.environ['TESTING_DB'] = TEST_DB_PATH

from app import app, inicializar_base_datos
from db_wrapper import get_db_connection

class VentasPOSSecurityTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        inicializar_base_datos()

    def setUp(self):
        self.app = app.test_client()

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Limpiar datos previos de pruebas
            cursor.execute("DELETE FROM clientes WHERE correo IN ('owner_empresa_a@test.com', 'seller_empresa_a@test.com', 'owner_empresa_b@test.com', 'client_empresa_b@test.com')")
            cursor.execute("DELETE FROM productos WHERE codigo IN ('PROD-A-01', 'PROD-B-01')")

            # 1. Crear Empresa A (Owner A y Seller A)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, empresa_nombre, activo)
                VALUES ('Owner A', 'owner_empresa_a@test.com', 'scrypt:test', 'admin', 'Empresa A', 1)
            """)
            cursor.execute("SELECT id FROM clientes WHERE correo = 'owner_empresa_a@test.com'")
            self.owner_a_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, empresa_nombre, creador_id, activo)
                VALUES ('Seller A', 'seller_empresa_a@test.com', 'scrypt:test', 'standard', 'Empresa A', ?, 1)
            """, (self.owner_a_id,))
            cursor.execute("SELECT id FROM clientes WHERE correo = 'seller_empresa_a@test.com'")
            self.seller_a_id = cursor.fetchone()[0]

            # 2. Crear Empresa B (Owner B y Cliente B de la empresa B)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, empresa_nombre, activo)
                VALUES ('Owner B', 'owner_empresa_b@test.com', 'scrypt:test', 'admin', 'Empresa B', 1)
            """)
            cursor.execute("SELECT id FROM clientes WHERE correo = 'owner_empresa_b@test.com'")
            self.owner_b_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, empresa_nombre, creador_id, activo)
                VALUES ('Cliente de Empresa B', 'client_empresa_b@test.com', 'scrypt:test', 'cliente', 'Empresa B', ?, 1)
            """, (self.owner_b_id,))
            cursor.execute("SELECT id FROM clientes WHERE correo = 'client_empresa_b@test.com'")
            self.client_b_id = cursor.fetchone()[0]

            # 3. Productos para Empresa A y Empresa B
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, cantidad, stock_reservado, precio_unitario, creador_id, activo)
                VALUES ('Empresa A', 'PROD-A-01', 'Laptop Empresa A', 10, 0, 1500.0, ?, 1)
            """, (self.owner_a_id,))
            cursor.execute("SELECT id FROM productos WHERE codigo = 'PROD-A-01'")
            self.prod_a_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, cantidad, stock_reservado, precio_unitario, creador_id, activo)
                VALUES ('Empresa B', 'PROD-B-01', 'Smartphone Empresa B', 20, 0, 800.0, ?, 1)
            """, (self.owner_b_id,))
            cursor.execute("SELECT id FROM productos WHERE codigo = 'PROD-B-01'")
            self.prod_b_id = cursor.fetchone()[0]

            conn.commit()

    def login(self, user_id, role='admin', name='Test User'):
        with self.app.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user_rol'] = role
            sess['user_nombre'] = name
            sess['session_token'] = 'dummy_token'

    def test_flujo_venta_pos_exitosa_y_descuento_stock(self):
        self.login(self.owner_a_id, 'admin', 'Owner A')

        payload = {
            'cliente_id': 0,
            'metodo_pago': 'efectivo',
            'descuento_porcentaje': 10.0,
            'items': [{'producto_id': self.prod_a_id, 'cantidad': 3, 'precio_unitario': 1500.0}]
        }

        response = self.app.post('/api/ventas/guardar', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total'], 4050.0)

        # Verificar descuento físico
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cantidad FROM productos WHERE id = ?", (self.prod_a_id,))
            self.assertEqual(cursor.fetchone()[0], 7)

    def test_bloqueo_inyeccion_producto_otro_tenant(self):
        """Un usuario de Empresa A NO puede vender un producto perteneciente a Empresa B (Anti-IDOR)"""
        self.login(self.owner_a_id, 'admin', 'Owner A')

        payload = {
            'cliente_id': 0,
            'metodo_pago': 'efectivo',
            'items': [{'producto_id': self.prod_b_id, 'cantidad': 1, 'precio_unitario': 800.0}]
        }

        response = self.app.post('/api/ventas/guardar', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('no pertenece a tu empresa', data['message'])

    def test_bloqueo_asignacion_cliente_otro_tenant(self):
        """Un usuario de Empresa A NO puede asignar la venta a un cliente de Empresa B"""
        self.login(self.owner_a_id, 'admin', 'Owner A')

        payload = {
            'cliente_id': self.client_b_id,
            'metodo_pago': 'efectivo',
            'items': [{'producto_id': self.prod_a_id, 'cantidad': 1, 'precio_unitario': 1500.0}]
        }

        response = self.app.post('/api/ventas/guardar', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('no pertenece a tu empresa', data['message'])

    def test_proteccion_descuento_invalido(self):
        """Descuentos negativos o >100% son acotados matemáticamente a 0%-100%"""
        self.login(self.owner_a_id, 'admin', 'Owner A')

        # Probar descuento negativo (-50%)
        payload = {
            'cliente_id': 0,
            'metodo_pago': 'efectivo',
            'descuento_porcentaje': -50.0,
            'items': [{'producto_id': self.prod_a_id, 'cantidad': 1, 'precio_unitario': 1500.0}]
        }
        res = self.app.post('/api/ventas/guardar', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['total'], 1500.0)  # No infla el precio

    def test_autorizacion_anulacion_vendedor_standard(self):
        """Vendedor standard solo puede anular ventas emitidas por él mismo"""
        # 1. Owner A hace una venta
        self.login(self.owner_a_id, 'admin', 'Owner A')
        payload = {
            'cliente_id': 0,
            'metodo_pago': 'efectivo',
            'items': [{'producto_id': self.prod_a_id, 'cantidad': 1, 'precio_unitario': 1500.0}]
        }
        res = self.app.post('/api/ventas/guardar', data=json.dumps(payload), content_type='application/json')
        venta_owner_id = res.get_json()['venta_id']

        # 2. Seller A intenta anular la venta del Owner -> Denegado
        self.login(self.seller_a_id, 'standard', 'Seller A')
        res_anular = self.app.post(f'/ventas/{venta_owner_id}/anular', content_type='application/json')
        self.assertEqual(res_anular.status_code, 403)
        self.assertFalse(res_anular.get_json()['success'])

        # 3. Seller A hace su propia venta y la anula -> Permitido
        payload_seller = {
            'cliente_id': 0,
            'metodo_pago': 'efectivo',
            'items': [{'producto_id': self.prod_a_id, 'cantidad': 1, 'precio_unitario': 1500.0}]
        }
        res_seller_sale = self.app.post('/api/ventas/guardar', data=json.dumps(payload_seller), content_type='application/json')
        venta_seller_id = res_seller_sale.get_json()['venta_id']

        res_seller_anular = self.app.post(f'/ventas/{venta_seller_id}/anular', content_type='application/json')
        self.assertEqual(res_seller_anular.status_code, 200)
        self.assertTrue(res_seller_anular.get_json()['success'])

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

if __name__ == '__main__':
    unittest.main()
