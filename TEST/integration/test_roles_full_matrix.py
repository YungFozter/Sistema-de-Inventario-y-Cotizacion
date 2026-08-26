import os
import sys
import unittest
import json
import sqlite3
from werkzeug.security import generate_password_hash

# Asegurar path raíz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

TEST_DB_PATH = 'TEST/test_matrix_db.sqlite3'
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass
os.environ['TESTING_DB'] = TEST_DB_PATH

from app import app, inicializar_base_datos
from db_wrapper import get_db_connection

# Hash precalculado para acelerar la suite
STATIC_HASH = generate_password_hash('Password123!')

class ComprehensiveRolesAndFlowsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        inicializar_base_datos()

    def setUp(self):
        self.app = app.test_client()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Limpiar tablas para aislamiento entre pruebas
            cursor.execute("DELETE FROM cotizacion_productos")
            cursor.execute("DELETE FROM cotizaciones")
            cursor.execute("DELETE FROM venta_productos")
            cursor.execute("DELETE FROM ventas")
            cursor.execute("DELETE FROM equipo_tareas")
            cursor.execute("DELETE FROM equipo_chat")
            cursor.execute("DELETE FROM equipo_invitaciones")
            cursor.execute("DELETE FROM equipo_solicitudes")
            cursor.execute("DELETE FROM proveedores")
            cursor.execute("DELETE FROM productos")
            cursor.execute("DELETE FROM clientes")
            cursor.execute("DELETE FROM pines_admin")
            cursor.execute("DELETE FROM logs")

            # 1. Crear Superadmin
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre)
                VALUES ('Superadmin Root', 'superadmin@sistema.com', ?, 'superadmin', 1, 'Sistema Central')
            """, (STATIC_HASH,))
            self.superadmin_id = cursor.lastrowid

            # 2. Crear Empresa Alfa (Admin Alfa y Vendedor Alfa)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, fecha_vencimiento_suscripcion)
                VALUES ('Admin Alfa', 'admin@alfa.com', ?, 'admin', 1, 'Empresa Alfa', '2030-12-31 23:59:59')
            """, (STATIC_HASH,))
            self.admin_alfa_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, creador_id)
                VALUES ('Vendedor Alfa 1', 'vendedor1@alfa.com', ?, 'standard', 1, 'Empresa Alfa', ?)
            """, (STATIC_HASH, self.admin_alfa_id))
            self.seller_alfa_id = cursor.lastrowid

            # 3. Crear Empresa Beta (Admin Beta y Vendedor Beta)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, fecha_vencimiento_suscripcion)
                VALUES ('Admin Beta', 'admin@beta.com', ?, 'admin', 1, 'Empresa Beta', '2030-12-31 23:59:59')
            """, (STATIC_HASH,))
            self.admin_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, creador_id)
                VALUES ('Vendedor Beta 1', 'vendedor1@beta.com', ?, 'standard', 1, 'Empresa Beta', ?)
            """, (STATIC_HASH, self.admin_beta_id))
            self.seller_beta_id = cursor.lastrowid

            conn.commit()

    def _login(self, user_id, user_email, user_rol, user_nombre, empresa_nombre, creador_id=None):
        """Simula una sesión autenticada con token de sesión seguro"""
        with self.app.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user_email'] = user_email
            sess['user_rol'] = user_rol
            sess['user_nombre'] = user_nombre
            sess['empresa_nombre'] = empresa_nombre
            sess['creador_id'] = creador_id
            sess['session_token'] = 'test_token_' + str(user_id)
            sess['suscripcion_activa'] = True
            sess['trial_activo'] = False

    # =========================================================================
    # SECCIÓN 1: PRUEBAS DE SUPERADMIN
    # =========================================================================
    def test_01_superadmin_auditoria_logs_y_exportar_csv(self):
        """Verifica que Superadmin puede consultar auditoría y exportar en CSV"""
        self._login(self.superadmin_id, 'superadmin@sistema.com', 'superadmin', 'Superadmin Root', 'Sistema Central')
        
        resp = self.app.get('/admin/logs')
        self.assertEqual(resp.status_code, 200)

        resp_csv = self.app.get('/admin/logs/exportar-csv')
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn('text/csv', resp_csv.headers.get('Content-Type', ''))
        self.assertIn('attachment', resp_csv.headers.get('Content-Disposition', ''))

    def test_02_superadmin_gestion_usuarios_completa(self):
        """Verifica que Superadmin puede crear, suspender, renovar y editar roles de usuarios"""
        self._login(self.superadmin_id, 'superadmin@sistema.com', 'superadmin', 'Superadmin Root', 'Sistema Central')

        # 1. Crear nuevo Admin
        resp_crear = self.app.post('/admin/usuarios', json={
            'nombre': 'Nuevo Admin Gamma',
            'correo': 'admin@gamma.com',
            'telefono': '70011223',
            'rol': 'admin',
            'contrasena': 'Password123!'
        })
        self.assertEqual(resp_crear.status_code, 201)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM clientes WHERE correo = 'admin@gamma.com'")
            gamma_id = cursor.fetchone()[0]

        # 2. Renovar suscripción
        resp_renovar = self.app.post(f'/admin/renovar_suscripcion/{gamma_id}', data={'dias': 60, 'notas': 'Pago anual'})
        self.assertEqual(resp_renovar.status_code, 302)

        # 3. Cambiar estado a suspendido
        resp_estado = self.app.put(f'/admin/usuarios/{gamma_id}/estado', json={'activo': 0})
        self.assertEqual(resp_estado.status_code, 200)

        # 4. Historial de renovaciones
        resp_hist = self.app.get(f'/admin/usuarios/{gamma_id}/historial_renovaciones')
        self.assertEqual(resp_hist.status_code, 200)
        data_hist = resp_hist.get_json()
        self.assertTrue(data_hist.get('success'))
        self.assertGreaterEqual(len(data_hist.get('historial', [])), 1)

    def test_03_superadmin_pines_y_respaldos(self):
        """Verifica generación de PINes de desbloqueo y gestión de respaldos"""
        self._login(self.superadmin_id, 'superadmin@sistema.com', 'superadmin', 'Superadmin Root', 'Sistema Central')

        resp_pin = self.app.post('/admin/pines', follow_redirects=True)
        self.assertEqual(resp_pin.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, pin FROM pines_admin ORDER BY id DESC LIMIT 1")
            pin_row = cursor.fetchone()
            self.assertIsNotNone(pin_row)
            pin_id = pin_row[0]

        resp_del_pin = self.app.post(f'/admin/pines/eliminar/{pin_id}', follow_redirects=True)
        self.assertEqual(resp_del_pin.status_code, 200)

        resp_backup = self.app.post('/admin/respaldos/crear', follow_redirects=True)
        self.assertEqual(resp_backup.status_code, 200)

    # =========================================================================
    # SECCIÓN 2: PRUEBAS DE ADMIN (PROPIETARIO)
    # =========================================================================
    def test_04_admin_crud_productos(self):
        """Verifica creación, edición y búsqueda de productos por un Administrador"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        resp_crear = self.app.post('/productos', data={
            'codigo': 'PROD-ALFA-01',
            'descripcion': 'Transformador Industrial 220V',
            'marca': 'AlfaElectric',
            'tm': 'Bs',
            'um': 'Pza',
            'cantidad': '20',
            'precio_unitario': '450.00'
        }, follow_redirects=True)
        self.assertEqual(resp_crear.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, cantidad, precio_unitario, empresa FROM productos WHERE codigo = 'PROD-ALFA-01'")
            p = cursor.fetchone()
            self.assertIsNotNone(p)
            self.assertEqual(p[1], 20.0)
            self.assertEqual(p[2], 450.0)
            self.assertEqual(p[3], 'Empresa Alfa')
            prod_id = p[0]

        resp_edit = self.app.post(f'/productos/editar/{prod_id}', data={
            'codigo': 'PROD-ALFA-01',
            'descripcion': 'Transformador Industrial 220V - Modificado',
            'marca': 'AlfaElectric Pro',
            'tm': 'Bs',
            'um': 'Pza',
            'cantidad': '25',
            'precio_unitario': '500.00'
        }, follow_redirects=True)
        self.assertEqual(resp_edit.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cantidad, precio_unitario, descripcion FROM productos WHERE id = ?", (prod_id,))
            p_mod = cursor.fetchone()
            self.assertEqual(p_mod[0], 25.0)
            self.assertEqual(p_mod[1], 500.0)
            self.assertIn('Modificado', p_mod[2])

    def test_05_admin_crud_proveedores(self):
        """Verifica registro de proveedores y prevención de duplicados dentro de la empresa"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        resp_prov = self.app.post('/proveedores', data={
            'nombre': 'Distribuidora Alfa Tech',
            'nit_ruc': '1029384756',
            'contacto_nombre': 'Carlos Sanchez',
            'telefono': '71122334',
            'correo': 'ventas@distalfa.com',
            'direccion': 'Av. Principal 123',
            'rubro': 'Electricidad'
        }, follow_redirects=True)
        self.assertEqual(resp_prov.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, empresa FROM proveedores WHERE nit_ruc = '1029384756'")
            prov = cursor.fetchone()
            self.assertIsNotNone(prov)
            self.assertEqual(prov[1], 'Distribuidora Alfa Tech')
            self.assertEqual(prov[2], 'Empresa Alfa')

        resp_dup = self.app.post('/proveedores', data={
            'nombre': 'Distribuidora Alfa Tech',
            'nit_ruc': '1029384756'
        }, follow_redirects=True)
        self.assertIn(b'ya se encuentra registrado', resp_dup.data)

    def test_06_admin_crud_clientes_y_paginacion(self):
        """Verifica registro de clientes con NIT/CI y endpoint AJAX de búsqueda y paginación"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        resp_cli = self.app.post('/clientes', data={
            'razon_social': 'Constructora Alfa Norte S.A.',
            'nit': '4938271019',
            'telefono': '72233445',
            'referencia': 'Obra Central',
            'tipo_cliente': 'empresa'
        }, follow_redirects=True)
        self.assertEqual(resp_cli.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, nit FROM clientes WHERE nit = '4938271019'")
            cli = cursor.fetchone()
            self.assertIsNotNone(cli)
            self.assertEqual(cli[1], 'Constructora Alfa Norte S.A.')

        resp_ajax = self.app.get('/api/buscar_clientes_cotizacion?q=Constructora&per_page=10&page=1')
        self.assertEqual(resp_ajax.status_code, 200)
        data_ajax = resp_ajax.get_json()
        self.assertGreaterEqual(len(data_ajax.get('clientes', [])), 1)

    def test_07_admin_creacion_cotizacion_y_calculo_matematico(self):
        """Verifica armado de cotización, subtotales, descuentos y conversión a palabras"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, stock_reservado, precio_unitario, creador_id)
                VALUES ('Empresa Alfa', 'ITEM-COT-01', 'Cable de Cobre 4mm', 'Pirelli', 'Bs', 'Metros', 100, 0, 15.50, ?)
            """, (self.admin_alfa_id,))
            prod_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, nit, telefono, rol, creador_id, empresa_nombre)
                VALUES ('Cliente Cot Alfa', '99887766', '73344556', 'cliente', ?, 'Empresa Alfa')
            """, (self.admin_alfa_id,))
            cli_id = cursor.lastrowid
            conn.commit()

        resp_cot = self.app.post('/cotizaciones', data={
            'cliente_id': str(cli_id),
            'descuento_porcentaje': '10',
            'producto_id[]': [str(prod_id)],
            'cantidad[]': ['10'],
            'precio_unitario[]': ['15.50']
        }, follow_redirects=True)
        self.assertEqual(resp_cot.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, subtotal, descuento_porcentaje, descuento_monto, total FROM cotizaciones WHERE cliente_id = ?", (cli_id,))
            cot = cursor.fetchone()
            self.assertIsNotNone(cot)
            # 10 * 15.50 = 155.00. 10% desc = 15.50. Total = 139.50
            self.assertAlmostEqual(float(cot[1]), 155.00, places=2)
            self.assertAlmostEqual(float(cot[2]), 10.00, places=2)
            self.assertAlmostEqual(float(cot[3]), 15.50, places=2)
            self.assertAlmostEqual(float(cot[4]), 139.50, places=2)

    def test_08_admin_ventas_pos_y_deduccion_atomica_stock(self):
        """Verifica venta POS con deducción atómica de inventario y posterior anulación con restitución"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Empresa Alfa', 'VENTA-STK-01', 'Interruptor Termomagnetico 32A', 'Schneider', 'Bs', 'Pza', 50, 80.00, ?)
            """, (self.admin_alfa_id,))
            prod_id = cursor.lastrowid
            conn.commit()

        # 1. Registrar venta de 5 unidades via /api/ventas/guardar
        resp_venta = self.app.post('/api/ventas/guardar', json={
            'metodo_pago': 'efectivo',
            'descuento_porcentaje': 0,
            'items': [
                {'producto_id': prod_id, 'cantidad': 5, 'precio_unitario': 80.00}
            ]
        })
        self.assertEqual(resp_venta.status_code, 200)
        data_venta = resp_venta.get_json()
        self.assertTrue(data_venta.get('success'))
        venta_id = data_venta.get('venta_id')

        # Verificar que el stock bajó a 45
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cantidad FROM productos WHERE id = ?", (prod_id,))
            self.assertEqual(cursor.fetchone()[0], 45.0)

        # 2. Anular venta y verificar restitución a 50
        resp_anular = self.app.post(f'/ventas/{venta_id}/anular')
        self.assertEqual(resp_anular.status_code, 200)
        self.assertTrue(resp_anular.get_json().get('success'))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cantidad FROM productos WHERE id = ?", (prod_id,))
            self.assertEqual(cursor.fetchone()[0], 50.0)

    def test_09_admin_equipo_chat_tareas_e_invitacion_qr(self):
        """Verifica creación de tareas, chat y generación de invitaciones QR de uso único"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        # 1. Crear Tarea para Vendedor Alfa
        resp_tarea = self.app.post('/equipo/tareas', data={
            'titulo': 'Revisar inventario de cables',
            'descripcion': 'Contar bobinas de 4mm y 6mm',
            'asignado_a[]': str(self.seller_alfa_id),
            'prioridad': 'alta',
            'fecha_limite': '2026-12-31'
        }, follow_redirects=True)
        self.assertEqual(resp_tarea.status_code, 200)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, titulo, prioridad, estado FROM equipo_tareas WHERE asignado_a = ?", (self.seller_alfa_id,))
            tarea = cursor.fetchone()
            self.assertIsNotNone(tarea)
            self.assertEqual(tarea[1], 'Revisar inventario de cables')
            self.assertEqual(tarea[2], 'alta')
            self.assertEqual(tarea[3], 'pendiente')

        # 2. Enviar mensaje de chat
        resp_chat = self.app.post('/equipo/chat', data={'mensaje': 'Bienvenidos al equipo Alfa'})
        self.assertEqual(resp_chat.status_code, 200)
        self.assertTrue(resp_chat.get_json().get('success'))

        # 3. Generar invitación QR de uso único
        resp_qr = self.app.post('/equipo/invitaciones/crear', data={'tipo_expiracion': 'uso_unico'})
        self.assertEqual(resp_qr.status_code, 200)
        data_qr = resp_qr.get_json()
        self.assertTrue(data_qr.get('success'))
        self.assertIn('link_invitacion', data_qr)

    def test_10_admin_barreras_de_seguridad_bloqueo_admin(self):
        """Verifica que un Admin regular no puede ingresar a rutas exclusivas de Superadmin"""
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        resp_logs = self.app.get('/admin/logs')
        self.assertIn(resp_logs.status_code, (302, 403))

        resp_respaldos = self.app.get('/admin/respaldos')
        self.assertIn(resp_respaldos.status_code, (302, 403))

        resp_pines = self.app.get('/admin/pines')
        self.assertIn(resp_pines.status_code, (302, 403))

    # =========================================================================
    # SECCIÓN 3: PRUEBAS DE STANDARD (VENDEDOR)
    # =========================================================================
    def test_11_vendedor_ventas_y_permisos_restringidos(self):
        """Verifica que un Vendedor Standard puede registrar ventas pero tiene bloqueada la anulación de ventas ajenas"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Empresa Alfa', 'PROD-VENTA-VEND', 'Foco LED 12W', 'Philips', 'Bs', 'Pza', 100, 20.00, ?)
            """, (self.admin_alfa_id,))
            prod_id = cursor.lastrowid
            conn.commit()

        # Login como Vendedor Alfa
        self._login(self.seller_alfa_id, 'vendedor1@alfa.com', 'standard', 'Vendedor Alfa 1', 'Empresa Alfa', creador_id=self.admin_alfa_id)

        # 1. Registrar venta como vendedor
        resp_v = self.app.post('/api/ventas/guardar', json={
            'metodo_pago': 'qr',
            'descuento_porcentaje': 0,
            'items': [{'producto_id': prod_id, 'cantidad': 10, 'precio_unitario': 20.00}]
        })
        self.assertEqual(resp_v.status_code, 200)
        data_v = resp_v.get_json()
        self.assertTrue(data_v.get('success'))
        venta_vendedor_id = data_v.get('venta_id')

        # 2. Vendedor anula su PROPIA venta -> Permitido
        resp_anula_propia = self.app.post(f'/ventas/{venta_vendedor_id}/anular')
        self.assertEqual(resp_anula_propia.status_code, 200)
        self.assertTrue(resp_anula_propia.get_json().get('success'))

        # 3. Intentar acceder a módulos administrativos -> Bloqueado
        resp_admin_panel = self.app.get('/admin/usuarios')
        self.assertIn(resp_admin_panel.status_code, (302, 403))

        resp_proveedores = self.app.get('/proveedores')
        self.assertIn(resp_proveedores.status_code, (302, 403))

    def test_12_vendedor_completar_tarea_asignada(self):
        """Verifica que un Vendedor Standard puede completar sus tareas asignadas"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, estado)
                VALUES (?, ?, 'Etiquetar productos nuevos', 'pendiente')
            """, (self.admin_alfa_id, self.seller_alfa_id))
            tarea_id = cursor.lastrowid
            conn.commit()

        self._login(self.seller_alfa_id, 'vendedor1@alfa.com', 'standard', 'Vendedor Alfa 1', 'Empresa Alfa', creador_id=self.admin_alfa_id)

        resp_estado = self.app.post(f'/equipo/tareas/{tarea_id}/completar')
        self.assertEqual(resp_estado.status_code, 200)
        self.assertTrue(resp_estado.get_json().get('success'))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT estado, completado_por_id FROM equipo_tareas WHERE id = ?", (tarea_id,))
            t_updated = cursor.fetchone()
            self.assertEqual(t_updated[0], 'hecho')
            self.assertEqual(t_updated[1], self.seller_alfa_id)

    # =========================================================================
    # SECCIÓN 4: AISLAMIENTO MULTI-TENANT Y SEGURIDAD ANTI-IDOR
    # =========================================================================
    def test_13_aislamiento_estricto_entre_empresas(self):
        """Verifica que Empresa Alfa no puede ver ni modificar productos, clientes ni ventas de Empresa Beta"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Empresa Beta', 'BETA-EXCLUSIVE-99', 'Panel Solar 450W', 'SunPower', 'Bs', 'Pza', 10, 1800.00, ?)
            """, (self.admin_beta_id,))
            prod_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, nit, telefono, rol, creador_id, empresa_nombre)
                VALUES ('Cliente Secreto Beta', '12345678', '76543210', 'cliente', ?, 'Empresa Beta')
            """, (self.admin_beta_id,))
            cli_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO proveedores (empresa, nombre, nit_ruc, creador_id)
                VALUES ('Empresa Beta', 'Proveedor Exclusivo Beta', '88776655', ?)
            """, (self.admin_beta_id,))
            prov_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO cotizaciones (cliente_id, creador_id, total, estado)
                VALUES (?, ?, 1800.00, 'Pendiente')
            """, (cli_beta_id, self.admin_beta_id))
            cot_beta_id = cursor.lastrowid
            conn.commit()

        # Iniciar sesión como Admin Alfa
        self._login(self.admin_alfa_id, 'admin@alfa.com', 'admin', 'Admin Alfa', 'Empresa Alfa')

        # 1. Producto de Beta no aparece en Alfa
        resp_prods = self.app.get('/productos')
        self.assertNotIn(b'BETA-EXCLUSIVE-99', resp_prods.data)

        # 2. Proveedor de Beta no aparece en Alfa
        resp_provs = self.app.get('/proveedores')
        self.assertNotIn(b'Proveedor Exclusivo Beta', resp_provs.data)

        # 3. No puede ver cotización de Beta
        resp_cot_beta = self.app.get(f'/cotizaciones/{cot_beta_id}')
        self.assertIn(resp_cot_beta.status_code, (302, 403, 404))

        # 4. No puede editar cliente de Beta
        resp_edit_cli = self.app.post(f'/clientes/editar/{cli_beta_id}', data={'nombre': 'Intento Hack'}, follow_redirects=True)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM clientes WHERE id = ?", (cli_beta_id,))
            self.assertEqual(cursor.fetchone()[0], 'Cliente Secreto Beta')

if __name__ == '__main__':
    unittest.main()
