import os
import sys
import unittest
import json
import sqlite3
from werkzeug.security import generate_password_hash

# Asegurar path raíz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

TEST_DB_PATH = 'TEST/test_e2e_backup_db.sqlite3'
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass
os.environ['TESTING_DB'] = TEST_DB_PATH

from app import app, inicializar_base_datos
from db_wrapper import get_db_connection

class RespaldoEmpresaAdminE2ETestCase(unittest.TestCase):
    """
    Test E2E a profundidad para la funcionalidad de 'Copia de Seguridad / Respaldo de mi Empresa'.
    Prueba el login real con las credenciales especificadas (ieeimendoza@gmail.com / enrique1),
    la descarga del archivo de respaldo JSON y la inspección completa de su estructura y contenido.
    """
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        inicializar_base_datos()

    def setUp(self):
        self.app = app.test_client()
        self.password_raw = 'enrique1'
        self.password_hash = generate_password_hash(self.password_raw)

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
            cursor.execute("DELETE FROM configuracion_pdf")
            cursor.execute("DELETE FROM logs")

            # 1. Crear el usuario Administrador solicitado
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, nit, telefono, fecha_vencimiento_suscripcion)
                VALUES ('Santiago Mendoza Soria', 'ieeimendoza@gmail.com', ?, 'admin', 1, 'Mendoza & Asociados Tech', '1029384756', '71234567', '2030-12-31 23:59:59')
            """, (self.password_hash,))
            self.admin_id = cursor.lastrowid

            # 2. Miembro del equipo (Vendedor)
            cursor.execute("""
                INSERT INTO clientes (nombre, correo, contrasena, rol, activo, empresa_nombre, creador_id)
                VALUES ('Carlos Vendedor', 'carlos@mendozatech.bo', ?, 'standard', 1, 'Mendoza & Asociados Tech', ?)
            """, (self.password_hash, self.admin_id))
            self.vendedor_id = cursor.lastrowid

            # 3. Clientes de la empresa
            cursor.execute("""
                INSERT INTO clientes (codigo_cliente, nombre, nit, telefono, correo, rol, creador_id, empresa_nombre)
                VALUES ('CLI-001', 'PANKIMIA SRL', '678263024', '72160066', 'contacto@pankimia.com', 'cliente', ?, 'Mendoza & Asociados Tech')
            """, (self.admin_id,))
            self.cliente_1_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO clientes (codigo_cliente, nombre, nit, telefono, correo, rol, creador_id, empresa_nombre)
                VALUES ('CLI-002', 'ROSIO VELEZ', '1015555020', '71061055', 'rosio@gmail.com', 'cliente', ?, 'Mendoza & Asociados Tech')
            """, (self.admin_id,))
            self.cliente_2_id = cursor.lastrowid

            # 4. Productos de la empresa
            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Mendoza & Asociados Tech', 'CAB-XL-100', 'Cable de Cobre Reforzado 100m', 'Chint', 'Bs', 'Rollo', 50, 450.00, ?)
            """, (self.admin_id,))
            self.prod_1_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, creador_id)
                VALUES ('Mendoza & Asociados Tech', 'DISY-32A', 'Disyuntor Termomagnético 32A', 'Schneider', 'Bs', 'Pza', 120, 85.50, ?)
            """, (self.admin_id,))
            self.prod_2_id = cursor.lastrowid

            # 5. Proveedor
            cursor.execute("""
                INSERT INTO proveedores (empresa, nombre, nit_ruc, contacto_nombre, telefono, correo, rubro, creador_id)
                VALUES ('Mendoza & Asociados Tech', 'Electrored Distribuidora SRL', '99887766', 'Ing. Ramiro Lopez', '76543210', 'ventas@electrored.bo', 'Material Eléctrico', ?)
            """, (self.admin_id,))
            self.prov_id = cursor.lastrowid

            # 6. Cotización emitida
            cursor.execute("""
                INSERT INTO cotizaciones (cliente_id, creador_id, codigo, subtotal, descuento_porcentaje, descuento_monto, total, estado, fecha)
                VALUES (?, ?, 'COT-2026-001', 985.50, 5.0, 49.28, 936.22, 'aprobada', '2026-08-26 10:00:00')
            """, (self.cliente_1_id, self.admin_id))
            self.cot_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO cotizacion_productos (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 2, 450.00, 900.00)
            """, (self.cot_id, self.prod_1_id))
            cursor.execute("""
                INSERT INTO cotizacion_productos (cotizacion_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 1, 85.50, 85.50)
            """, (self.cot_id, self.prod_2_id))

            # 7. Venta POS
            cursor.execute("""
                INSERT INTO ventas (codigo_venta, total, metodo_pago, estado_pago, vendedor_id, creador_id, empresa, fecha)
                VALUES ('VTA-2026-001', 450.00, 'qr', 'completado', ?, ?, 'Mendoza & Asociados Tech', '2026-08-26 11:30:00')
            """, (self.vendedor_id, self.admin_id))
            self.venta_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO venta_productos (venta_id, producto_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 1, 450.00, 450.00)
            """, (self.venta_id, self.prod_1_id))

            # 8. Tarea del equipo
            cursor.execute("""
                INSERT INTO equipo_tareas (creador_id, asignado_a, titulo, descripcion, prioridad, estado)
                VALUES (?, ?, 'Entregar bobinas de cable a Pankimia', 'Coordinar con transporte', 'alta', 'en_progreso')
            """, (self.admin_id, self.vendedor_id))
            self.tarea_id = cursor.lastrowid

            # 9. Configuración de PDF
            cursor.execute("""
                INSERT INTO configuracion_pdf (usuario_id, tipo_hoja, color_tema, nota_pie, terminos_condiciones)
                VALUES (?, 'A4', '#FF6B35', 'Gracias por su preferencia', 'Validez de oferta: 15 días')
            """, (self.admin_id,))

            conn.commit()

    def test_e2e_flujo_completo_login_descarga_y_apertura_respaldo_empresa(self):
        """
        Flujo E2E completo:
        1. Login con ieeimendoza@gmail.com / enrique1
        2. Navegación al dashboard
        3. Petición de exportación del Respaldo de Empresa (/empresa/respaldo/exportar)
        4. Verificación de cabeceras HTTP y formato JSON
        5. Apertura y parseo del archivo entregado
        6. Inspección exhaustiva de cada bloque de datos
        """
        # 1. Login Real
        resp_login = self.app.post('/login', data={
            'correo': 'ieeimendoza@gmail.com',
            'contrasena': self.password_raw
        }, follow_redirects=True)
        self.assertEqual(resp_login.status_code, 200)

        # 2. Descargar el archivo de Respaldo de Empresa
        resp_export = self.app.get('/empresa/respaldo/exportar')
        self.assertEqual(resp_export.status_code, 200)
        self.assertIn('application/json', resp_export.content_type)
        
        content_disposition = resp_export.headers.get('Content-Disposition', '')
        self.assertIn('attachment;', content_disposition)
        self.assertIn('respaldo_empresa_Mendoza', content_disposition)

        # 3. Abrir e inspeccionar el archivo entregado
        backup_json_str = resp_export.data.decode('utf-8')
        backup_data = json.loads(backup_json_str)

        # A. Inspeccionar Metadatos
        self.assertIn('metadata_respaldo', backup_data)
        meta = backup_data['metadata_respaldo']
        self.assertEqual(meta['tipo'], 'RESPALDO_EMPRESA_TENANT')
        self.assertEqual(meta['version_formato'], '2.0')
        self.assertEqual(meta['generado_por']['correo'], 'ieeimendoza@gmail.com')
        self.assertEqual(meta['generado_por']['nombre'], 'Santiago Mendoza Soria')
        self.assertEqual(meta['empresa']['nombre'], 'Mendoza & Asociados Tech')
        self.assertEqual(meta['empresa']['nit'], '1029384756')

        # B. Inspeccionar Resumen Estadístico
        stats = meta['resumen_estadisticas']
        self.assertEqual(stats['total_productos'], 2)
        self.assertEqual(stats['total_clientes'], 2)
        self.assertEqual(stats['total_proveedores'], 1)
        self.assertEqual(stats['total_cotizaciones'], 1)
        self.assertEqual(stats['total_ventas'], 1)
        self.assertEqual(stats['miembros_equipo'], 1)
        self.assertEqual(stats['total_tareas'], 1)

        # C. Inspeccionar Catálogo de Productos
        self.assertIn('productos', backup_data)
        prods = backup_data['productos']
        self.assertEqual(len(prods), 2)
        codigos = [p['codigo'] for p in prods]
        self.assertIn('CAB-XL-100', codigos)
        self.assertIn('DISY-32A', codigos)
        cable = next(p for p in prods if p['codigo'] == 'CAB-XL-100')
        self.assertEqual(cable['stock_fisico'], 50.0)
        self.assertEqual(cable['precio_unitario'], 450.0)

        # D. Inspeccionar Cartera de Clientes
        self.assertIn('clientes', backup_data)
        clis = backup_data['clientes']
        self.assertEqual(len(clis), 2)
        cli_nombres = [c['nombre'] for c in clis]
        self.assertIn('PANKIMIA SRL', cli_nombres)
        self.assertIn('ROSIO VELEZ', cli_nombres)

        # E. Inspeccionar Proveedores
        self.assertIn('proveedores', backup_data)
        provs = backup_data['proveedores']
        self.assertEqual(len(provs), 1)
        self.assertEqual(provs[0]['nombre'], 'Electrored Distribuidora SRL')
        self.assertEqual(provs[0]['contacto_nombre'], 'Ing. Ramiro Lopez')

        # F. Inspeccionar Cotizaciones y sus Ítems Detallados
        self.assertIn('cotizaciones', backup_data)
        cots = backup_data['cotizaciones']
        self.assertEqual(len(cots), 1)
        cot = cots[0]
        self.assertEqual(cot['id'], self.cot_id)
        self.assertEqual(cot['total'], 936.22)
        self.assertEqual(len(cot['items']), 2)
        self.assertEqual(cot['items'][0]['producto_codigo'], 'CAB-XL-100')

        # G. Inspeccionar Ventas POS y sus Ítems Detallados
        self.assertIn('ventas', backup_data)
        vtas = backup_data['ventas']
        self.assertEqual(len(vtas), 1)
        vta = vtas[0]
        self.assertEqual(vta['codigo_venta'], 'VTA-2026-001')
        self.assertEqual(vta['metodo_pago'], 'qr')
        self.assertEqual(vta['total'], 450.0)
        self.assertEqual(len(vta['items']), 1)

        # H. Inspeccionar Equipo y Tareas
        self.assertIn('equipo', backup_data)
        self.assertEqual(len(backup_data['equipo']), 1)
        self.assertEqual(backup_data['equipo'][0]['nombre'], 'Carlos Vendedor')

        self.assertIn('tareas', backup_data)
        self.assertEqual(len(backup_data['tareas']), 1)
        self.assertEqual(backup_data['tareas'][0]['titulo'], 'Entregar bobinas de cable a Pankimia')
        self.assertEqual(backup_data['tareas'][0]['prioridad'], 'alta')

        # I. Inspeccionar Configuración PDF
        self.assertIn('configuracion_pdf', backup_data)
        self.assertEqual(backup_data['configuracion_pdf']['tipo_hoja'], 'A4')
        self.assertEqual(backup_data['configuracion_pdf']['color_tema'], '#FF6B35')

        # Imprimir resumen de apertura exitosa
        print(f"\n[OK E2E] Archivo de Respaldo generado y verificado con exito:")
        print(f" - Nombre del archivo: {content_disposition}")
        print(f" - Empresa: {meta['empresa']['nombre']}")
        print(f" - Tamano JSON: {len(backup_json_str)} bytes")
        print(f" - Resumen: {json.dumps(stats, indent=2)}")

if __name__ == '__main__':
    unittest.main()
