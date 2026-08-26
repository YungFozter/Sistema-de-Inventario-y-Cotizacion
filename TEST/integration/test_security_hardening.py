import os
import sys
import unittest
import json
import sqlite3
from werkzeug.security import generate_password_hash

# Asegurar path raíz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

TEST_DB_PATH = 'TEST/test_security_hardening_db.sqlite3'
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass
os.environ['TESTING_DB'] = TEST_DB_PATH

from app import app, inicializar_base_datos
from db_wrapper import get_db_connection

STATIC_HASH = generate_password_hash('SecPassword123!')

class SecurityHardeningAuditTestCase(unittest.TestCase):
    """
    Suite de Verificación de Seguridad, Prevención de Fugas de Información (Anti-IDOR),
    Defensa contra Inyecciones SQL, Protección de Sesión y Control Estricto de Privilegios (RBAC).
    """
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        inicializar_base_datos()

    def setUp(self):
        self.app = app.test_client()
        with get_db_connection() as conn:
            cursor = conn.cursor()
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

            # 1. Superadmin
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre)
                VALUES ('Root Superadmin', 'superadmin@security.com', ?, 'superadmin', 1, 'Sistema Central')
            """, (STATIC_HASH,))
            self.superadmin_id = cursor.lastrowid

            # 2. Tenant Alfa (Empresa Alfa)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, fecha_vencimiento_suscripcion)
                VALUES ('Admin Alfa Corp', 'admin@alfacorp.com', ?, 'admin', 1, 'Alfa Corp', '2030-12-31 23:59:59')
            """, (STATIC_HASH,))
            self.admin_alfa_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, creador_id)
                VALUES ('Vendedor Alfa 1', 'vendedor@alfacorp.com', ?, 'standard', 1, 'Alfa Corp', ?)
            """, (STATIC_HASH, self.admin_alfa_id))
            self.seller_alfa_id = cursor.lastrowid

            # 3. Tenant Beta (Empresa Beta - Víctima de pruebas de ataque)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, fecha_vencimiento_suscripcion)
                VALUES ('Admin Beta Corp', 'admin@betacorp.com', ?, 'admin', 1, 'Beta Corp', '2030-12-31 23:59:59')
            """, (STATIC_HASH,))
            self.admin_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, creador_id)
                VALUES ('Vendedor Beta 1', 'vendedor@betacorp.com', ?, 'standard', 1, 'Beta Corp', ?)
            """, (STATIC_HASH, self.admin_beta_id))
            self.seller_beta_id = cursor.lastrowid

            # Crear datos confidenciales en Tenant Beta
            cursor.execute("""
                INSERT INTO clientes (nombre, nit, telefono, rol, creador_id, empresa_nombre)
                VALUES ('Cliente Confidencial Beta', '888777666', '79998888', 'cliente', ?, 'Beta Corp')
            """, (self.admin_beta_id,))
            self.client_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Beta Corp', 'PROD-SECRET-BETA', 'Fórmula Secreta Componente X', 'BetaLab', 'Bs', 'Litros', 500, 1500.00, ?)
            """, (self.admin_beta_id,))
            self.prod_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO proveedores (empresa, nombre, nit_ruc, creador_id)
                VALUES ('Beta Corp', 'Proveedor Exclusivo Beta', '999888777', ?)
            """, (self.admin_beta_id,))
            self.prov_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO cotizaciones (cliente_id, creador_id, total, subtotal, estado, fecha)
                VALUES (?, ?, 3000.00, 3000.00, 'pendiente', '2026-08-26 12:00:00')
            """, (self.client_beta_id, self.admin_beta_id))
            self.cot_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO cotizacion_productos (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 2, 1500.00, 3000.00)
            """, (self.cot_beta_id, self.prod_beta_id))

            cursor.execute("""
                INSERT INTO ventas (codigo_venta, total, metodo_pago, estado_pago, vendedor_id, creador_id, empresa)
                VALUES ('VTA-BETA-001', 1500.00, 'efectivo', 'completado', ?, ?, 'Beta Corp')
            """, (self.seller_beta_id, self.admin_beta_id))
            self.venta_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO venta_productos (venta_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 1, 1500.00, 1500.00)
            """, (self.venta_beta_id, self.prod_beta_id))

            cursor.execute("""
                INSERT INTO equipo_chat (usuario_id, mensaje, fecha)
                VALUES (?, 'Plan estratégico confidencial de Beta Corp', '2026-08-26 12:00:00')
            """, (self.admin_beta_id,))
            self.chat_beta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, descripcion, estado)
                VALUES (?, ?, 'Auditar finanzas internas', 'Detalles privados', 'pendiente')
            """, (self.admin_beta_id, self.seller_beta_id))
            self.task_beta_id = cursor.lastrowid

            conn.commit()

    def _login(self, user_id, user_email, user_rol, user_nombre, empresa_nombre, creador_id=None):
        with self.app.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user_email'] = user_email
            sess['user_rol'] = user_rol
            sess['user_nombre'] = user_nombre
            sess['empresa_nombre'] = empresa_nombre
            sess['creador_id'] = creador_id
            sess['session_token'] = f'token_{user_id}'
            sess['suscripcion_activa'] = True
            sess['trial_activo'] = False

    # =========================================================================
    # 1. DEFENSA CONTRA INYECCIÓN SQL (SQLi)
    # =========================================================================
    def test_01_sqli_authentication_bypass_attempt(self):
        """Verifica que intentos de bypass de autenticación por SQLi son completamente neutralizados"""
        payloads = [
            "' OR '1'='1",
            "admin@alfacorp.com' --",
            "' UNION SELECT 1, 'hacked', 'hacked', 'admin', 1 --",
            "admin' or 1=1#"
        ]
        for p in payloads:
            resp = self.app.post('/login', data={'correo': p, 'contrasena': 'anything'}, follow_redirects=True)
            self.assertTrue(b'Credenciales incorrectas' in resp.data or b'Demasiados intentos' in resp.data)
            with self.app.session_transaction() as sess:
                self.assertIsNone(sess.get('user_id'))

    def test_02_sqli_search_and_filter_neutralization(self):
        """Verifica que inyecciones SQL en parámetros de búsqueda AJAX no rompen ni extraen datos"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        sqli_queries = [
            "'; DROP TABLE clientes; --",
            "' UNION SELECT id, nombre, 'hack', 'hack', 'hack', 'hack' FROM clientes --",
            "Constructora' OR '1'='1"
        ]
        for q in sqli_queries:
            resp = self.app.get(f'/api/buscar_clientes_cotizacion?q={q}')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            # No debe listar el cliente confidencial de Beta
            nombres = [c.get('nombre') for c in data.get('clientes', [])]
            self.assertNotIn('Cliente Confidencial Beta', nombres)

    # =========================================================================
    # 2. AISLAMIENTO MULTI-TENANT Y PREVENCIÓN DE ROBO DE INFORMACIÓN (ANTI-IDOR)
    # =========================================================================
    def test_03_anti_idor_bloqueo_acceso_cotizaciones_ajenas(self):
        """Verifica que Tenant Alfa no puede ver ni descargar el PDF de la cotización de Tenant Beta"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # 1. Intento de ver detalle HTML de cotización de Beta
        resp_view = self.app.get(f'/cotizaciones/{self.cot_beta_id}')
        self.assertIn(resp_view.status_code, (302, 403, 404))

        # 2. Intento de descargar PDF de cotización de Beta
        resp_pdf = self.app.get(f'/cotizaciones/{self.cot_beta_id}/pdf')
        self.assertIn(resp_pdf.status_code, (302, 403, 404))

    def test_04_anti_idor_bloqueo_tampering_clientes(self):
        """Verifica que Tenant Alfa no puede editar ni borrar clientes de Tenant Beta"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # Intento de editar
        resp_edit = self.app.post(f'/clientes/editar/{self.client_beta_id}', data={
            'nombre': 'Cliente Secuestrado por Alfa',
            'nit': '00000000',
            'telefono': '00000000'
        }, follow_redirects=True)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM clientes WHERE id = ?", (self.client_beta_id,))
            self.assertEqual(cursor.fetchone()[0], 'Cliente Confidencial Beta')

    def test_05_anti_idor_bloqueo_tampering_productos_y_stock(self):
        """Verifica que Tenant Alfa no puede modificar productos ni alterar inventario de Tenant Beta"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # Intento de editar producto secreto de Beta
        resp_edit_p = self.app.post(f'/productos/editar/{self.prod_beta_id}', data={
            'codigo': 'HACKED-CODE',
            'descripcion': 'Producto Saboteado',
            'marca': 'Hacked',
            'tm': 'Bs',
            'um': 'Litros',
            'cantidad': '0',
            'precio_unitario': '1.00'
        }, follow_redirects=True)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT codigo, cantidad, precio_unitario FROM productos WHERE id = ?", (self.prod_beta_id,))
            p = cursor.fetchone()
            self.assertEqual(p[0], 'PROD-SECRET-BETA')
            self.assertEqual(p[1], 500.0)
            self.assertEqual(p[2], 1500.0)

    def test_06_anti_idor_bloqueo_tampering_ventas_y_anulacion(self):
        """Verifica que Tenant Alfa no puede anular ni ver ventas de Tenant Beta"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # Intento de anular venta de Beta
        resp_anular = self.app.post(f'/ventas/{self.venta_beta_id}/anular')
        self.assertIn(resp_anular.status_code, (403, 404))

        # Verificar que el estado de la venta sigue intacto
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT estado_pago FROM ventas WHERE id = ?", (self.venta_beta_id,))
            self.assertEqual(cursor.fetchone()[0], 'completado')

    def test_07_anti_idor_bloqueo_espionaje_chat_y_tareas(self):
        """Verifica que mensajes y tareas internas de Beta Corp son invisibles para Alfa Corp"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # 1. Obtener mensajes del chat
        resp_chat = self.app.get('/equipo/chat/obtener')
        if resp_chat.status_code == 200:
            data_chat = resp_chat.get_json()
            mensajes = [m.get('mensaje') for m in data_chat.get('mensajes', [])]
            self.assertNotIn('Plan estratégico confidencial de Beta Corp', mensajes)

        # 2. Intento de completar tarea ajena
        resp_task = self.app.post(f'/equipo/tareas/{self.task_beta_id}/completar')
        self.assertIn(resp_task.status_code, (403, 404))

    # =========================================================================
    # 3. CONTROL DE PRIVILEGIOS (RBAC) Y PREVENCIÓN DE ESCALADA
    # =========================================================================
    def test_08_bloqueo_escalada_privilegios_vendedor_standard(self):
        """Verifica que un Vendedor Standard no puede crear usuarios, cambiar roles ni acceder a configuración administrativa"""
        self._login(self.seller_alfa_id, 'vendedor@alfacorp.com', 'standard', 'Vendedor Alfa 1', 'Alfa Corp', creador_id=self.admin_alfa_id)

        # Intento de crear un usuario Admin
        resp_crear = self.app.post('/admin/usuarios', json={
            'nombre': 'Atacante Elevado',
            'correo': 'hacker@alfacorp.com',
            'rol': 'admin',
            'contrasena': 'SecPassword123!'
        })
        self.assertIn(resp_crear.status_code, (302, 403))

        # Intento de auto-promover su propio rol a admin
        resp_rol = self.app.put(f'/admin/usuarios/{self.seller_alfa_id}/rol', json={'rol': 'admin'})
        self.assertIn(resp_rol.status_code, (302, 403))

    def test_09_bloqueo_acceso_respaldos_y_logs_a_admins_regulares(self):
        """Verifica que un Administrador de Tenant no puede descargar backups del sistema ni ver logs de otros tenants"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        # Intento de entrar a panel de logs
        resp_logs = self.app.get('/admin/logs')
        self.assertIn(resp_logs.status_code, (302, 403))

        # Intento de entrar a respaldos
        resp_respaldos = self.app.get('/admin/respaldos')
        self.assertIn(resp_respaldos.status_code, (302, 403))

        # Intento de descargar backup directamente
        resp_dl = self.app.get('/admin/respaldos/descargar/test_backup.sqlite3')
        self.assertIn(resp_dl.status_code, (302, 403))

    # =========================================================================
    # 4. PREVENCIÓN DE PATH TRAVERSAL & SEGURIDAD DE ARCHIVOS
    # =========================================================================
    def test_10_prevencion_path_traversal_en_descarga_respaldos(self):
        """Verifica que intentos de Path Traversal (ej. ../../app.py) son neutralizados sanitizando nombres de archivo"""
        self._login(self.superadmin_id, 'superadmin@security.com', 'superadmin', 'Root Superadmin', 'Sistema Central')

        # Intento de Path Traversal
        resp_traversal = self.app.get('/admin/respaldos/descargar/..%2F..%2Fapp.py')
        # Debe redirigir con error o retornar 404 seguro, nunca el código fuente de app.py
        self.assertNotIn(b'from flask import Flask', resp_traversal.data)

    # =========================================================================
    # 5. INTEGRIDAD ATÓMICA DE TRANSACCIONES (PREVENCIÓN DE PÉRDIDA DE DATOS)
    # =========================================================================
    def test_11_transaccion_atomica_en_fallo_de_venta(self):
        """Verifica que si una venta falla por producto inexistente o stock negativo, NO hay deducción parcial ni registros huérfanos"""
        self._login(self.admin_alfa_id, 'admin@alfacorp.com', 'admin', 'Admin Alfa Corp', 'Alfa Corp')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Alfa Corp', 'PROD-ATOMIC-01', 'Item Integridad 1', 'Test', 'Bs', 'Pza', 10, 50.00, ?)
            """, (self.admin_alfa_id,))
            p1_id = cursor.lastrowid
            conn.commit()

        # Enviar venta mixta: Producto 1 válido (5 u), Producto 2 inválido (ID 999999)
        resp_fail = self.app.post('/api/ventas/guardar', json={
            'metodo_pago': 'efectivo',
            'items': [
                {'producto_id': p1_id, 'cantidad': 5, 'precio_unitario': 50.00},
                {'producto_id': 999999, 'cantidad': 1, 'precio_unitario': 100.00}
            ]
        })
        self.assertIn(resp_fail.status_code, (400, 403, 404, 500))

        # Verificar que el stock de p1 se mantuvo exactamente en 10 (Rollback atómico)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cantidad FROM productos WHERE id = ?", (p1_id,))
            self.assertEqual(cursor.fetchone()[0], 10.0)

            # Verificar que no se creó ninguna venta corrupta
            cursor.execute("SELECT COUNT(*) FROM ventas WHERE creador_id = ?", (self.admin_alfa_id,))
            self.assertEqual(cursor.fetchone()[0], 0)

if __name__ == '__main__':
    unittest.main()
