import os
import sqlite3
from db_wrapper import get_db_connection
import json
from datetime import datetime


# =============================================
# FUNCIONES DE INICIALIZACIÓN (SQLite puro)
# =============================================

def crear_tablas():
    """Crea todas las tablas necesarias en la base de datos"""
    if not os.path.exists('database'):
        os.makedirs('database')

    conexion = get_db_connection()
    cursor = conexion.cursor()
    
    is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))

    try:
        # Tabla de logs/auditoría
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS logs (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER,
                accion TEXT NOT NULL,
                detalle TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de clientes/usuarios
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS clientes (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
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
        ''')

        # Tabla de categorías
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS categorias (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activo {"BOOLEAN DEFAULT TRUE" if is_postgres else "BOOLEAN DEFAULT 1"}
            ){";" if is_postgres else ""}
        ''')

        # Tabla de productos
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS productos (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
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
        ''')

        # Tabla de cotizaciones
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
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
        ''')

        # Tabla de productos en cotizaciones
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS cotizacion_productos (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                cotizacion_id INTEGER,
                producto_id INTEGER,
                cantidad INTEGER,
                precio_unitario REAL,
                subtotal REAL,
                descuento REAL DEFAULT 0,
                FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de importaciones desde PDF
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS importaciones_pdf (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre_importacion TEXT NOT NULL,
                fecha_importacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER,
                total_items INTEGER DEFAULT 0,
                estado TEXT DEFAULT 'pendiente',
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de items extraídos de PDF
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS items_importados_temp (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
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
        ''')

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


def registrar_log(usuario_id, accion, detalle=None):
    """
    Registra una acción en el log de auditoría
    
    Args:
        usuario_id (int): ID del usuario que realizó la acción (puede ser None)
        accion (str): Tipo de acción realizada
        detalle (dict): Detalles adicionales sobre la acción
    """
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        # Convertir el detalle a JSON si no es None
        detalle_json = json.dumps(detalle) if detalle is not None else None
        
        # Insertar el registro
        cursor.execute(
            'INSERT INTO logs (usuario_id, accion, detalle, fecha) VALUES (?, ?, ?, ?)',
            (usuario_id, accion, detalle_json, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        
        conexion.commit()
        
    except Exception as e:
        print(f"Error al registrar log: {e}")
    finally:
        if 'conexion' in locals():
            conexion.close()

def migrar_clientes_existentes():
    """Asigna creador_id a clientes existentes y crea admin por defecto si es necesario"""
    conexion = get_db_connection()
    cursor = conexion.cursor()

    try:
        # Verificar si existe al menos un admin
        cursor.execute('''
            SELECT id FROM clientes 
            WHERE rol IN ('admin', 'superadmin') 
            ORDER BY id LIMIT 1
        ''')
        admin = cursor.fetchone()
        admin_id = admin[0] if admin else None

        if not admin_id:
            # Crear admin por defecto
            cursor.execute('''
                INSERT INTO clientes (
                    nombre, correo, rol, creador_id, activo
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                'Admin Por Defecto',
                'admin@default.com',
                'admin',
                1,
                1
            ))
            admin_id = cursor.lastrowid
            conexion.commit()
            print(f"[OK] Admin por defecto creado con ID {admin_id}")

        # Actualizar clientes existentes
        cursor.execute('''
            UPDATE clientes 
            SET creador_id = ?
            WHERE creador_id IS NULL OR creador_id = 0
        ''', (admin_id,))

        conexion.commit()
        print(f"[OK] Asignado creador_id={admin_id} a {cursor.rowcount} clientes existentes")

    except Exception as e:
        print(f"[ERROR] Error en migración de clientes: {str(e)}")
        conexion.rollback()
        raise
    finally:
        conexion.close()


def migrar_productos_categorias():
    """Agregar columna categoria_id a la tabla productos si no existe"""
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        # Verificar si la columna categoria_id ya existe
        cursor.execute("PRAGMA table_info(productos)")
        columnas = cursor.fetchall()
        columnas_nombres = [col[1] for col in columnas]
        
        if 'categoria_id' not in columnas_nombres:
            print("[INFO] Agregando columna categoria_id a la tabla productos...")
            cursor.execute("ALTER TABLE productos ADD COLUMN categoria_id INTEGER")
            print("[OK] Columna categoria_id agregada correctamente")
        else:
            print("[OK] Columna categoria_id ya existe en productos")
        
        conexion.commit()
        conexion.close()
        
    except Exception as e:
        print(f"[ERROR] Error en migración de productos: {str(e)}")
        if conexion:
            conexion.rollback()
            conexion.close()
        raise


def inicializar_base_datos():
    """Inicialización completa de la base de datos con SQLite puro"""
    print("\n" + "=" * 50)
    print(" INICIALIZACIÓN DE BASE DE DATOS (SQLite)")
    print("=" * 50)

    try:
        crear_tablas()
        migrar_clientes_existentes()

        print("\n" + "=" * 50)
        print(" BASE DE DATOS PREPARADA CORRECTAMENTE")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"[ERROR] Error crítico durante inicialización: {str(e)}")
        raise


# =============================================
# FUNCIONES PARA IMPORTACIÓN DE PRODUCTOS PDF
# =============================================

def guardar_importacion_pdf(nombre_importacion, items, usuario_id=None):
    """
    Guarda un nuevo lote de importación de productos con un nombre único y sus celdas extraídas.
    Garantiza que no se sobrescriban importaciones agregando sello de hora si ya existe el mismo nombre.
    """
    conexion = get_db_connection()
    cursor = conexion.cursor()
    try:
        now_dt = datetime.now()
        if not nombre_importacion or not nombre_importacion.strip():
            nombre_importacion = f"Importación - {now_dt.strftime('%d/%m/%Y %H:%M')}"

        nombre_importacion = nombre_importacion.strip()

        # Verificar si el nombre ya existe para evitar sobrescritura
        cursor.execute('SELECT COUNT(*) FROM importaciones_pdf WHERE nombre_importacion = ?', (nombre_importacion,))
        if cursor.fetchone()[0] > 0:
            nombre_importacion = f"{nombre_importacion} ({now_dt.strftime('%H:%M:%S')})"

        cursor.execute('''
            INSERT INTO importaciones_pdf (nombre_importacion, usuario_id, total_items, estado)
            VALUES (?, ?, ?, ?)
        ''', (nombre_importacion, usuario_id, len(items), 'guardado'))
        
        importacion_id = cursor.lastrowid

        for item in items:
            cursor.execute('''
                INSERT INTO items_importados_temp (importacion_id, codigo, descripcion, marca, um, precio_unitario)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                importacion_id,
                item.get('codigo', ''),
                item.get('descripcion', ''),
                item.get('marca', ''),
                item.get('um', 'Pza'),
                float(item.get('precio_unitario', 0.0) or 0.0)
            ))

        conexion.commit()
        return importacion_id, nombre_importacion
    except Exception as e:
        conexion.rollback()
        print(f"[ERROR] Error al guardar importación PDF: {e}")
        raise
    finally:
        conexion.close()



def obtener_importaciones_pdf():
    """Retorna la lista de todas las importaciones realizadas"""
    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    try:
        cursor.execute('''
            SELECT id, nombre_importacion, fecha_importacion, total_items, estado
            FROM importaciones_pdf
            ORDER BY id DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conexion.close()


def obtener_importacion_por_id(importacion_id):
    """Obtiene los detalles y los items de una importación específica"""
    conexion = get_db_connection()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    try:
        cursor.execute('SELECT * FROM importaciones_pdf WHERE id = ?', (importacion_id,))
        imp = cursor.fetchone()
        if not imp:
            return None, []
        cursor.execute('SELECT * FROM items_importados_temp WHERE importacion_id = ? ORDER BY id ASC', (importacion_id,))
        items = [dict(row) for row in cursor.fetchall()]
        return dict(imp), items

    finally:
        conexion.close()


def registrar_productos_seleccionados(items, empresa="General", categoria_id=None, respetar_cantidades=True):
    """
    Inserta o actualiza un grupo de productos importados en la tabla oficial 'productos'.
    Si respetar_cantidades es True, guarda la cantidad real extraída (ej: 5.5 MTS, 26, etc.).
    """
    conexion = get_db_connection()
    cursor = conexion.cursor()
    registrados_count = 0
    
    try:
        for item in items:
            codigo = str(item.get('codigo', '')).strip()[:50]
            descripcion = str(item.get('descripcion', '')).strip()[:500]
            marca = str(item.get('marca', '')).strip()[:100]

            um = str(item.get('um', 'Pza')).strip() or 'Pza'
            precio_unitario = float(item.get('precio_unitario', 0.0) or 0.0)
            empresa_item = str(item.get('empresa', empresa)).strip() or 'General'

            if respetar_cantidades and 'cantidad' in item:
                try:
                    cantidad = float(item['cantidad'])
                except (ValueError, TypeError):
                    cantidad = 999.0
            else:
                cantidad = 999.0

            precio_total = round(cantidad * precio_unitario, 2)

            if not codigo and not descripcion:
                continue

            # Verificar si el producto ya existe (por empresa y código)
            cursor.execute('SELECT id, cantidad FROM productos WHERE empresa = ? AND codigo = ?', (empresa_item, codigo))
            existente = cursor.fetchone()

            if existente:
                # Si ya existe y respetamos cantidades, sumar la cantidad para no perder stock de repeticiones
                if respetar_cantidades and existente[1] is not None and existente[1] != 999:
                    final_cantidad = round(float(existente[1]) + cantidad, 2)
                else:
                    final_cantidad = cantidad

                final_precio_total = round(final_cantidad * precio_unitario, 2)

                cursor.execute('''
                    UPDATE productos
                    SET descripcion = ?, marca = ?, um = ?, cantidad = ?, precio_unitario = ?, precio_total = ?, categoria_id = ?, es_importado = 1, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (descripcion, marca, um, final_cantidad, precio_unitario, final_precio_total, categoria_id, existente[0]))
            else:
                cursor.execute('''
                    INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, es_importado)
                    VALUES (?, ?, ?, ?, 'Bs', ?, ?, ?, ?, ?, 1)
                ''', (empresa_item, codigo, descripcion, marca, um, cantidad, precio_unitario, precio_total, categoria_id))


            
            # Si el item venía de una importación guardada, marcarlo como registrado
            if item.get('temp_id'):
                cursor.execute('UPDATE items_importados_temp SET registrado = 1 WHERE id = ?', (item['temp_id'],))

            registrados_count += 1

        conexion.commit()
        return registrados_count
    except Exception as e:
        conexion.rollback()
        print(f"[ERROR] Error al registrar productos seleccionados: {e}")
        raise
    finally:
        conexion.close()


def eliminar_importacion_pdf(importacion_id):
    """Elimina una importación guardada y sus ítems temporales asociados"""
    conexion = get_db_connection()
    cursor = conexion.cursor()
    try:
        cursor.execute('DELETE FROM items_importados_temp WHERE importacion_id = ?', (importacion_id,))
        cursor.execute('DELETE FROM importaciones_pdf WHERE id = ?', (importacion_id,))
        conexion.commit()
        return True
    except Exception as e:
        conexion.rollback()
        print(f"[ERROR] Error al eliminar importación: {e}")
        raise
    finally:
        conexion.close()

