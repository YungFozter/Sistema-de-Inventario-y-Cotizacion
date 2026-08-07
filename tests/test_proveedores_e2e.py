import unittest
import os
import json
import tempfile
import sqlite3

# Set test environment
os.environ['TESTING_DB'] = '1'

from app import app
from db_wrapper import get_db_connection
from models import crear_tablas, migrar_columnas_nuevas_productos, migrar_columnas_nuevas_clientes

class TestProveedoresE2E(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Preparar base de datos
        crear_tablas()
        migrar_columnas_nuevas_clientes()
        migrar_columnas_nuevas_productos()

        # Simular sesión de usuario admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_rol'] = 'admin'
            sess['user_nombre'] = 'Admin Test'

    def test_01_crear_y_listar_proveedor(self):
        """Verifica la creación y listado de un nuevo proveedor."""
        response = self.client.post('/proveedores', data={
            'nombre': 'Siemens Bolivia Test',
            'nit_ruc': '1092837401',
            'contacto_nombre': 'Carlos Mendoza',
            'telefono': '71234567',
            'correo': 'contacto@siemens.bo',
            'direccion': 'Av. Equipetrol 100',
            'rubro': 'Material Eléctrico'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verificar inserción en DB
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, nit_ruc FROM proveedores WHERE nombre = 'Siemens Bolivia Test'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 'Siemens Bolivia Test')
            self.assertEqual(row[1], '1092837401')

    def test_02_api_proveedores_json(self):
        """Verifica el endpoint API JSON de lista de proveedores."""
        response = self.client.get('/api/proveedores')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('proveedores'), list)

    def test_03_asociar_proveedor_a_producto_y_filtrar(self):
        """Verifica el registro de producto asignado a un proveedor y su filtrado por búsqueda."""
        # Insertar producto con proveedor
        response = self.client.post('/productos', data={
            'empresa': 'ElectroTest SRL',
            'codigo': 'PROV-ITEM-TEST-003',
            'descripcion': 'Interruptor Termomagnético 32A',
            'marca': 'Siemens',
            'proveedor': 'Siemens Bolivia Test',
            'tm': 'Bs',
            'um': 'Pza',
            'cantidad': '20',
            'precio_unitario': '45.50'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Filtrar por proveedor vía GET
        filter_resp = self.client.get('/productos?proveedor=Siemens')
        self.assertEqual(filter_resp.status_code, 200)
        self.assertIn(b'PROV-ITEM-TEST-003', filter_resp.data)

if __name__ == '__main__':
    unittest.main()
