import sqlite3
import unittest

def generar_codigo_cliente_unico(cursor, creador_id=None):
    usados = set()
    try:
        if creador_id:
            cursor.execute("SELECT codigo_cliente FROM clientes WHERE creador_id = ? AND codigo_cliente LIKE ? AND rol = 'cliente'", (creador_id, 'CLI-%'))
        else:
            cursor.execute("SELECT codigo_cliente FROM clientes WHERE codigo_cliente LIKE ? AND rol = 'cliente'", ('CLI-%',))
        rows = cursor.fetchall() or []
        for row in rows:
            if not row: continue
            try:
                cod = row[0] if isinstance(row, tuple) or isinstance(row, list) else row.get('codigo_cliente') if isinstance(row, dict) else row[0]
                if cod and isinstance(cod, str):
                    cod = cod.upper()
                    parts = cod.split('-')
                    if len(parts) >= 2 and parts[1].isdigit():
                        usados.add(int(parts[1]))
            except: pass
    except: pass
    num = 1
    while num in usados:
        num += 1
    return f"CLI-{num:04d}"

class TestCodigoCliente(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE clientes (id INTEGER PRIMARY KEY, creador_id INTEGER, codigo_cliente TEXT, rol TEXT)''')

    def test_generacion_inicial(self):
        self.assertEqual(generar_codigo_cliente_unico(self.cursor, 1), 'CLI-0001')

    def test_generacion_con_existentes(self):
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (1, 'CLI-0001', 'cliente')")
        self.assertEqual(generar_codigo_cliente_unico(self.cursor, 1), 'CLI-0002')

    def test_relleno_huecos(self):
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (1, 'CLI-0001', 'cliente')")
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (1, 'CLI-0003', 'cliente')")
        self.assertEqual(generar_codigo_cliente_unico(self.cursor, 1), 'CLI-0002')

    def test_aislamiento_admin(self):
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (2, 'CLI-0001', 'cliente')")
        self.assertEqual(generar_codigo_cliente_unico(self.cursor, 1), 'CLI-0001')

    def test_case_insensitive_y_rol(self):
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (1, 'cli-0001', 'cliente')")
        self.cursor.execute("INSERT INTO clientes (creador_id, codigo_cliente, rol) VALUES (1, 'CLI-0002', 'admin')")
        # CLI-0002 is admin, so it should be ignored. cli-0001 is treated as CLI-0001.
        # Wait, if CLI-0002 is ignored, then next is CLI-0002.
        self.assertEqual(generar_codigo_cliente_unico(self.cursor, 1), 'CLI-0002')

if __name__ == '__main__':
    unittest.main()
