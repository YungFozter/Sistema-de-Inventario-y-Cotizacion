import os
import re

def patch_models():
    filepath = r"f:\Proyectos\ProyectoCotizacion\ProyectoCotizacion\models.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_crear_tablas = '''def crear_tablas():
    """Crea todas las tablas necesarias en la base de datos"""
    if not os.path.exists('database'):
        os.makedirs('database')

    conexion = get_db_connection()
    cursor = conexion.cursor()
    
    is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))

    try:
        # Tabla de logs/auditoría
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS logs (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER,
                accion TEXT NOT NULL,
                detalle TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de clientes/usuarios
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS clientes (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre TEXT NOT NULL,
                nit TEXT,
                codigo_cliente TEXT,
                telefono TEXT,
                referencia TEXT,
                correo TEXT UNIQUE,
                contrasena TEXT,
                rol TEXT NOT NULL DEFAULT 'standard',
                tipo_cliente TEXT DEFAULT 'normal',
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activo {"BOOLEAN DEFAULT TRUE" if is_postgres else "BOOLEAN DEFAULT 1"},
                creador_id INTEGER,
                FOREIGN KEY (creador_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de categorías
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS categorias (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activo {"BOOLEAN DEFAULT TRUE" if is_postgres else "BOOLEAN DEFAULT 1"}
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de productos
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS productos (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                empresa TEXT NOT NULL,
                codigo TEXT NOT NULL,
                descripcion TEXT,
                marca TEXT,
                tm TEXT DEFAULT 'Bs',
                um TEXT DEFAULT 'UN',
                cantidad INTEGER DEFAULT 0,
                precio_unitario REAL,
                precio_total REAL,
                categoria_id INTEGER,
                categoria TEXT,
                stock_minimo INTEGER DEFAULT 5,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                es_importado INTEGER DEFAULT 0,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id),
                UNIQUE(empresa, codigo)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de cotizaciones
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                cliente_id INTEGER,
                creador_id INTEGER,
                codigo TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total REAL,
                estado TEXT DEFAULT 'pendiente',
                descuento_porcentaje REAL DEFAULT 0.0,
                descuento_monto REAL DEFAULT 0.0,
                subtotal REAL DEFAULT 0.0,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                FOREIGN KEY (creador_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de productos en cotizaciones
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS cotizacion_productos (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                cotizacion_id INTEGER,
                producto_id INTEGER,
                cantidad INTEGER,
                precio_unitario REAL,
                subtotal REAL,
                descuento REAL DEFAULT 0,
                FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de importaciones desde PDF
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS importaciones_pdf (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre_importacion TEXT NOT NULL,
                fecha_importacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER,
                total_items INTEGER DEFAULT 0,
                estado TEXT DEFAULT 'pendiente',
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Tabla de items extraídos de PDF
        cursor.execute(f\'\'\'
            CREATE TABLE IF NOT EXISTS items_importados_temp (
                id {"SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                importacion_id INTEGER NOT NULL,
                codigo TEXT,
                descripcion TEXT,
                marca TEXT,
                um TEXT DEFAULT 'Pza',
                precio_unitario REAL DEFAULT 0.0,
                registrado {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                producto_registrado_id INTEGER,
                FOREIGN KEY (importacion_id) REFERENCES importaciones_pdf(id) ON DELETE CASCADE,
                FOREIGN KEY (producto_registrado_id) REFERENCES productos(id)
            ){";" if is_postgres else ""}
        \'\'\')

        # Insertar categorías por defecto
        categorias_defecto = [
            ('Electrónica', 'Equipos y componentes electrónicos'),
            ('Papelería', 'Productos de oficina y papelería'),
            ('Herramientas', 'Herramientas de trabajo y construcción'),
            ('Alimentos', 'Productos alimenticios'),
            ('Textil', 'Productos textiles y vestimenta'),
            ('Hogar', 'Artículos para el hogar'),
            ('Automóviles', 'Productos y repuestos automotrices'),
            ('Salud', 'Productos médicos y de salud'),
            ('Deportes', 'Artículos deportivos'),
            ('Otros', 'Productos no clasificados')
        ]
        
        for nombre, descripcion in categorias_defecto:
            if is_postgres:
                cursor.execute(
                    'INSERT INTO categorias (nombre, descripcion) VALUES (%s, %s) ON CONFLICT (nombre) DO NOTHING',
                    (nombre, descripcion)
                )
            else:
                cursor.execute(
                    'INSERT OR IGNORE INTO categorias (nombre, descripcion) VALUES (?, ?)',
                    (nombre, descripcion)
                )

        conexion.commit()
        
        print("[OK] Tablas creadas/verificadas correctamente.")
    except Exception as e:
        print(f"[ERROR] Error al crear tablas: {str(e)}")
        conexion.rollback()
        raise
    finally:
        conexion.close()
'''

    # Reemplazar la función crear_tablas entera
    # Buscamos desde def crear_tablas(): hasta el inicio de def registrar_log(
    content = re.sub(
        r'def crear_tablas\(\):.*?def registrar_log\(',
        new_crear_tablas + '\n\ndef registrar_log(',
        content,
        flags=re.DOTALL
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    patch_models()
    print("Models patched.")
