import os
import sys
import json
import unittest

# Forzar el directorio raíz del proyecto en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['TESTING_DB'] = '1'

from app import app
from db_wrapper import get_db_connection
from models import inicializar_base_datos, registrar_productos_seleccionados
from utils.exchange_rate import obtener_tipo_cambio_paralelo

class TestCustomFieldsAndColumnMapperE2E(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Inicializa la base de datos de pruebas."""
        inicializar_base_datos()
        cls.client = app.test_client()
        cls.app_context = app.app_context()
        cls.app_context.push()

    def setUp(self):
        """Prepara un cliente de prueba con sesión activa."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 9999
            sess['user_rol'] = 'admin'
            sess['user_nombre'] = 'Admin Pruebas E2E'

        # Insertar o asegurar usuario de prueba en clientes
        with get_db_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM clientes WHERE id = 9999")
            cur.execute("""
                INSERT INTO clientes (id, nombre, correo, contrasena, rol, empresa_nombre)
                VALUES (9999, 'Admin Pruebas E2E', 'admin_e2e@empresa.com', 'hash', 'admin', 'Empresa E2E')
            """)
            con.commit()

    def tearDown(self):
        """Limpia registros creados durante la prueba."""
        with get_db_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM productos WHERE empresa = 'Empresa E2E'")
            cur.execute("DELETE FROM clientes WHERE id = 9999")
            con.commit()

    def test_01_configuracion_campos_personalizados_api(self):
        """Prueba E2E: Guardar y consultar configuración de campos personalizados por empresa."""
        campos_test = ['Ubicación Almacén', 'Garantía Meses', 'Nº Lote']
        
        # POST para guardar la configuración
        res_post = self.client.post('/api/empresa/campos-config', json={'campos': campos_test})
        self.assertEqual(res_post.status_code, 200)
        data_post = res_post.get_json()
        self.assertTrue(data_post['success'])
        self.assertEqual(data_post['campos'], campos_test)

        # GET para verificar lectura
        res_get = self.client.get('/api/empresa/campos-config')
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.get_json()
        self.assertTrue(data_get['success'])
        self.assertEqual(data_get['campos'], campos_test)

    def test_02_registro_producto_con_campos_personalizados(self):
        """Prueba E2E: Registrar productos con campos personalizados y verificar almacenamiento JSON."""
        items_importacion = [
            {
                'codigo': 'E2E-101',
                'descripcion': 'Cable Cobre Multifilar 10AWG',
                'marca': 'Conduspar',
                'um': 'Metros',
                'cantidad': 150,
                'precio_unitario': 12.50,
                'empresa': 'Empresa E2E',
                'campos_personalizados': {
                    'Ubicación Almacén': 'Estante A-4',
                    'Garantía Meses': '24',
                    'Nº Lote': 'LT-2026-X'
                }
            }
        ]

        count = registrar_productos_seleccionados(items_importacion, empresa='Empresa E2E', respetar_cantidades=True)
        self.assertEqual(count, 1)

        # Consultar producto de la base de datos
        with get_db_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT codigo, descripcion, campos_personalizados FROM productos WHERE empresa = 'Empresa E2E' AND codigo = 'E2E-101'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 'E2E-101')

            campos_db = json.loads(row[2])
            self.assertEqual(campos_db.get('Ubicación Almacén'), 'Estante A-4')
            self.assertEqual(campos_db.get('Garantía Meses'), '24')
            self.assertEqual(campos_db.get('Nº Lote'), 'LT-2026-X')

    def test_03_tipo_cambio_paralelo_airtm_live(self):
        """Prueba E2E: Servicio de Tipo de Cambio Paralelo AirTm Live."""
        rate_info = obtener_tipo_cambio_paralelo()
        self.assertIn('rate', rate_info)
        self.assertGreater(rate_info['rate'], 0)
        self.assertIn('source', rate_info)

if __name__ == '__main__':
    unittest.main()
