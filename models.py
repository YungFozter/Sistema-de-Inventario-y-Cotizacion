import os
import sqlite3
from db_wrapper import get_db_connection
import json
from datetime import datetime, timezone, timedelta

def obtener_fecha_bolivia():
    """Devuelve la fecha y hora actual en la zona horaria de Bolivia (UTC-4)"""
    return datetime.now(timezone(timedelta(hours=-4)))


# =============================================
# FUNCIONES DE INICIALIZACIÓN (SQLite puro)
# =============================================

def crear_tablas():
    """Crea todas las tablas necesarias en la base de datos"""
    if not os.path.exists('database'):
        os.makedirs('database')

    conexion = get_db_connection()
    cursor = conexion.cursor()
    
    is_postgres = bool(
        not os.environ.get('TESTING_DB') and
        os.environ.get('DATABASE_URL') and
        os.environ.get('DATABASE_URL').startswith('postgres')
    )


    try:
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
                empresa_nombre TEXT,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultima_conexion TIMESTAMP,
                session_token TEXT,
                activo {"BOOLEAN DEFAULT TRUE" if is_postgres else "BOOLEAN DEFAULT 1"},
                creador_id INTEGER,
                cotizaciones_trial_usadas INTEGER DEFAULT 0,
                auth_provider TEXT DEFAULT 'local',
                FOREIGN KEY (creador_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

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

        # Tabla de categorías
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS categorias (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                nombre TEXT NOT NULL,
                descripcion TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activo {"BOOLEAN DEFAULT TRUE" if is_postgres else "BOOLEAN DEFAULT 1"},
                creador_id INTEGER,
                FOREIGN KEY (creador_id) REFERENCES clientes(id)
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
                stock_reservado INTEGER DEFAULT 0,
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

        # Tabla de pines de administrador
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS pines_admin (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                pin TEXT NOT NULL UNIQUE,
                usado {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usado_por INTEGER,
                FOREIGN KEY (usado_por) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de historial de renovaciones
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS historial_renovaciones (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                admin_id INTEGER,
                dias_agregados INTEGER NOT NULL,
                fecha_renovacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                superadmin_id INTEGER,
                notas TEXT,
                FOREIGN KEY (admin_id) REFERENCES clientes(id),
                FOREIGN KEY (superadmin_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de chat de equipo
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_chat (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                es_fijado {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de tareas de equipo
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_tareas (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                creador_id INTEGER NOT NULL,
                asignado_a INTEGER,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                prioridad TEXT DEFAULT 'media',
                estado TEXT DEFAULT 'pendiente',
                completado_por_id INTEGER,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_completada TIMESTAMP,
                FOREIGN KEY (creador_id) REFERENCES clientes(id),
                FOREIGN KEY (asignado_a) REFERENCES clientes(id),
                FOREIGN KEY (completado_por_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de notificaciones de equipo
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_notificaciones (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                tipo TEXT DEFAULT 'tarea_completada',
                leido {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Tabla de configuración personalizada de PDF ("MI PDF")
        asegurar_tabla_configuracion_pdf(cursor)

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
                cursor.execute('SELECT id FROM categorias WHERE nombre = %s', (nombre,))
                if not cursor.fetchone():
                    cursor.execute(
                        'INSERT INTO categorias (nombre, descripcion) VALUES (%s, %s)',
                        (nombre, descripcion)
                    )
            else:
                cursor.execute(
                    'INSERT OR IGNORE INTO categorias (nombre, descripcion) VALUES (?, ?)',
                    (nombre, descripcion)
                )

        conexion.commit()

        # Sanitizar nombres de empresas (seguro en PostgreSQL y SQLite)
        try:
            if is_postgres:
                cursor.execute("UPDATE productos SET empresa = TRIM(REGEXP_REPLACE(empresa, E'[\\t\\r\\n]+', '', 'g')) WHERE empresa IS NOT NULL")
                
                # Activar RLS (Row Level Security) en Supabase para resolver avisos de seguridad
                tablas_rls = [
                    'clientes', 'logs', 'categorias', 'productos', 'cotizaciones',
                    'cotizacion_productos', 'importaciones_pdf', 'items_importados_temp',
                    'configuracion_pdf', 'pines_admin', 'historial_renovaciones'
                ]
                for t in tablas_rls:
                    try:
                        cursor.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY;")
                    except Exception:
                        pass
            else:
                cursor.execute("UPDATE productos SET empresa = TRIM(REPLACE(empresa, char(9), '')) WHERE empresa IS NOT NULL")
            conexion.commit()
        except Exception as err_clean:
            print(f"[WARN] No se pudo limpiar empresa o activar RLS: {str(err_clean)}")
        
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
                True
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


def migrar_esquema_productos():
    """Agrega columnas faltantes a la tabla productos (categoria_id, stock_reservado)"""
    conexion = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        is_postgres = bool(
            not os.environ.get('TESTING_DB') and
            os.environ.get('DATABASE_URL') and
            os.environ.get('DATABASE_URL').startswith('postgres')
        )

        
        if is_postgres:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='productos'")
            rows = cursor.fetchall()
            columnas_existentes = []
            for col in rows:
                if isinstance(col, (dict, list, tuple)):
                    columnas_existentes.append(col[0])
                else:
                    columnas_existentes.append(getattr(col, 'column_name', col[0]))
            
            if 'categoria_id' not in columnas_existentes:
                print("[INFO] Agregando columna categoria_id a la tabla productos (Postgres)...")
                cursor.execute("ALTER TABLE productos ADD COLUMN categoria_id INTEGER")
                print("[OK] Columna categoria_id agregada")
                
            if 'stock_reservado' not in columnas_existentes:
                print("[INFO] Agregando columna stock_reservado a la tabla productos (Postgres)...")
                cursor.execute("ALTER TABLE productos ADD COLUMN stock_reservado INTEGER DEFAULT 0")
                print("[OK] Columna stock_reservado agregada")
        else:
            cursor.execute("PRAGMA table_info(productos)")
            columnas = [col[1] for col in cursor.fetchall()]
            
            if 'categoria_id' not in columnas:
                print("[INFO] Agregando columna categoria_id a la tabla productos (SQLite)...")
                cursor.execute("ALTER TABLE productos ADD COLUMN categoria_id INTEGER")
                print("[OK] Columna categoria_id agregada")
                
            if 'stock_reservado' not in columnas:
                print("[INFO] Agregando columna stock_reservado a la tabla productos (SQLite)...")
                cursor.execute("ALTER TABLE productos ADD COLUMN stock_reservado INTEGER DEFAULT 0")
                print("[OK] Columna stock_reservado agregada")
        
        conexion.commit()
    except Exception as e:
        print(f"[ERROR] Error en migración de esquema de productos: {str(e)}")
        if conexion:
            try:
                conexion.rollback()
            except Exception:
                pass
    finally:
        if conexion:
            try:
                conexion.close()
            except Exception:
                pass

def migrar_columnas_nuevas_categorias():
    """Agrega creador_id a categorias y quita el UNIQUE de nombre."""
    conexion = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        is_postgres = bool(
            not os.environ.get('TESTING_DB') and
            os.environ.get('DATABASE_URL') and
            os.environ.get('DATABASE_URL').startswith('postgres')
        )

        
        if is_postgres:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='categorias'")
            rows = cursor.fetchall()
            columnas_existentes = []
            for col in rows:
                if isinstance(col, (dict, list, tuple)):
                    columnas_existentes.append(col[0])
                else:
                    columnas_existentes.append(getattr(col, 'column_name', col[0]))
            
            if 'creador_id' not in columnas_existentes:
                print("[INFO] Agregando columna creador_id a la tabla categorias (Postgres)...")
                cursor.execute("ALTER TABLE categorias ADD COLUMN creador_id INTEGER REFERENCES clientes(id)")
                try:
                    cursor.execute("ALTER TABLE categorias DROP CONSTRAINT categorias_nombre_key")
                except Exception as e:
                    print(f"[WARN] No se pudo eliminar la restriccion UNIQUE en categorias (Postgres): {e}")
                print("[OK] Columna creador_id agregada y UNIQUE removido")
        else:
            cursor.execute("PRAGMA table_info(categorias)")
            columnas = [col[1] for col in cursor.fetchall()]
            
            if 'creador_id' not in columnas:
                print("[INFO] Agregando columna creador_id a la tabla categorias (SQLite)...")
                cursor.execute("PRAGMA foreign_keys=off;")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categorias_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT NOT NULL,
                        descripcion TEXT,
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        activo BOOLEAN DEFAULT 1,
                        creador_id INTEGER,
                        FOREIGN KEY (creador_id) REFERENCES clientes(id)
                    )
                ''')
                
                cursor.execute('''
                    INSERT INTO categorias_new (id, nombre, descripcion, fecha_creacion, activo)
                    SELECT id, nombre, descripcion, fecha_creacion, activo FROM categorias
                ''')
                
                cursor.execute("DROP TABLE categorias")
                cursor.execute("ALTER TABLE categorias_new RENAME TO categorias")
                cursor.execute("PRAGMA foreign_keys=on;")
                print("[OK] Tabla categorias migrada en SQLite (agregado creador_id y eliminada restricción UNIQUE)")
        
        conexion.commit()
    except Exception as e:
        print(f"[ERROR] Error en migración de esquema de categorias: {str(e)}")
        if conexion:
            try:
                conexion.rollback()
            except Exception:
                pass
    finally:
        if conexion:
            try:
                conexion.close()
            except Exception:
                pass

migrar_productos_categorias = migrar_esquema_productos


def inicializar_base_datos():
    """Inicialización completa de la base de datos con SQLite puro"""
    print("\n" + "=" * 50)
    print(" INICIALIZACIÓN DE BASE DE DATOS (SQLite)")
    print("=" * 50)

    try:
        crear_tablas()
        migrar_clientes_existentes()
        migrar_columnas_nuevas_categorias()
        migrar_columna_auth_provider()

        print("\n" + "=" * 50)
        print(" BASE DE DATOS PREPARADA CORRECTAMENTE")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"[ERROR] Error crítico durante inicialización: {str(e)}")
        raise

def migrar_columna_auth_provider():
    """Agrega la columna auth_provider a la tabla clientes si no existe"""
    conexion = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        is_postgres = bool(
            not os.environ.get('TESTING_DB') and
            os.environ.get('DATABASE_URL') and
            os.environ.get('DATABASE_URL').startswith('postgres')
        )

        if is_postgres:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clientes'")
            rows = cursor.fetchall()
            columnas = [col[0] for col in rows if isinstance(col, (list, tuple))] if rows else []
            if 'auth_provider' not in columnas:
                cursor.execute("ALTER TABLE clientes ADD COLUMN auth_provider TEXT DEFAULT 'local'")
                print("[OK] Columna auth_provider agregada en PostgreSQL")
        else:
            cursor.execute("PRAGMA table_info(clientes)")
            columnas = [col[1] for col in cursor.fetchall()]
            if 'auth_provider' not in columnas:
                cursor.execute("ALTER TABLE clientes ADD COLUMN auth_provider TEXT DEFAULT 'local'")
                print("[OK] Columna auth_provider agregada en SQLite")
        
        conexion.commit()
    except Exception as e:
        print(f"[ERROR] Error en migración auth_provider: {str(e)}")
        if conexion:
            try:
                conexion.rollback()
            except Exception:
                pass
    finally:
        if conexion:
            try:
                conexion.close()
            except Exception:
                pass

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
        now_dt = obtener_fecha_bolivia()
        fecha_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

        if not nombre_importacion or not nombre_importacion.strip():
            nombre_importacion = f"Importación - {now_dt.strftime('%d/%m/%Y %H:%M')}"

        nombre_importacion = nombre_importacion.strip()

        # Verificar si el nombre ya existe para evitar sobrescritura
        cursor.execute('SELECT COUNT(*) FROM importaciones_pdf WHERE nombre_importacion = ?', (nombre_importacion,))
        if cursor.fetchone()[0] > 0:
            nombre_importacion = f"{nombre_importacion} ({now_dt.strftime('%H:%M:%S')})"

        is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))
        if is_postgres:
            cursor.execute('''
                INSERT INTO importaciones_pdf (nombre_importacion, fecha_importacion, usuario_id, total_items, estado)
                VALUES (?, ?, ?, ?, ?) RETURNING id
            ''', (nombre_importacion, fecha_str, usuario_id, len(items), 'guardado'))
            row = cursor.fetchone()
            importacion_id = row[0] if row else getattr(cursor, 'lastrowid', None)
        else:
            cursor.execute('''
                INSERT INTO importaciones_pdf (nombre_importacion, fecha_importacion, usuario_id, total_items, estado)
                VALUES (?, ?, ?, ?, ?)
            ''', (nombre_importacion, fecha_str, usuario_id, len(items), 'guardado'))
            importacion_id = cursor.lastrowid

        if not importacion_id:
            cursor.execute('SELECT id FROM importaciones_pdf WHERE nombre_importacion = ? ORDER BY id DESC LIMIT 1', (nombre_importacion,))
            row = cursor.fetchone()
            if row:
                importacion_id = row[0]

        for item in items:
            try:
                pu = float(item.get('precio_unitario', 0.0) or 0.0)
            except (ValueError, TypeError):
                pu = 0.0

            cursor.execute('''
                INSERT INTO items_importados_temp (importacion_id, codigo, descripcion, marca, um, precio_unitario)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                importacion_id,
                item.get('codigo', ''),
                item.get('descripcion', ''),
                item.get('marca', ''),
                item.get('um', 'Pza'),
                pu
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
        rows = cursor.fetchall()
        importaciones = []
        tz_bolivia = timezone(timedelta(hours=-4))
        for r in rows:
            d = dict(r)
            fi = d.get('fecha_importacion')
            if isinstance(fi, datetime):
                if fi.tzinfo is not None:
                    fi = fi.astimezone(tz_bolivia)
                d['fecha_importacion'] = fi.strftime('%d/%m/%Y %H:%M:%S')
            elif isinstance(fi, str) and fi:
                try:
                    dt = datetime.fromisoformat(fi.replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(tz_bolivia)
                    d['fecha_importacion'] = dt.strftime('%d/%m/%Y %H:%M:%S')
                except Exception:
                    d['fecha_importacion'] = str(fi)
            importaciones.append(d)
        return importaciones
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


def registrar_productos_seleccionados(items, empresa="General", categoria_id=None, respetar_cantidades=True, tipo_documento="factura"):
    """
    Inserta o actualiza un grupo de productos importados en la tabla oficial 'productos'.
    Si respetar_cantidades es True, guarda la cantidad extraída.
    Dependiendo de tipo_documento ('factura' o 'catalogo') se actualiza el stock real o se deja en 0.
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
                    cantidad_extraida = float(item['cantidad'])
                except (ValueError, TypeError):
                    cantidad_extraida = 999.0
            else:
                cantidad_extraida = 999.0

            if not codigo and not descripcion:
                continue

            # Verificar si el producto ya existe (por empresa y código)
            cursor.execute('SELECT id, cantidad FROM productos WHERE empresa = ? AND codigo = ?', (empresa_item, codigo))
            existente = cursor.fetchone()

            if existente:
                # Si ya existe, calculamos la nueva cantidad según el tipo de documento
                stock_actual = float(existente[1]) if existente[1] is not None and existente[1] != 999 else 0.0
                
                if tipo_documento == 'factura' and respetar_cantidades:
                    final_cantidad = round(stock_actual + cantidad_extraida, 2)
                else:
                    final_cantidad = stock_actual # Mantiene el stock intacto para 'catalogo' o sin cantidad
                
                final_precio_total = round(final_cantidad * precio_unitario, 2)

                cursor.execute('''
                    UPDATE productos
                    SET descripcion = ?, marca = ?, um = ?, cantidad = ?, precio_unitario = ?, precio_total = ?, categoria_id = ?, es_importado = 1, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (descripcion, marca, um, final_cantidad, precio_unitario, final_precio_total, categoria_id, existente[0]))
            else:
                # Si es nuevo
                if tipo_documento == 'catalogo':
                    final_cantidad = 0.0
                else:
                    final_cantidad = cantidad_extraida if respetar_cantidades else 999.0
                    
                final_precio_total = round(final_cantidad * precio_unitario, 2)
                
                cursor.execute('''
                    INSERT INTO productos (empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, es_importado)
                    VALUES (?, ?, ?, ?, 'Bs', ?, ?, ?, ?, ?, 1)
                ''', (empresa_item, codigo, descripcion, marca, um, final_cantidad, precio_unitario, final_precio_total, categoria_id))

            
            # Si el item venía de una importación guardada, marcarlo como registrado
            if item.get('temp_id'):
                cursor.execute('UPDATE items_importados_temp SET registrado = TRUE WHERE id = ?', (item['temp_id'],))

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


def migrar_tablas_equipo():
    """Garantiza la creación de las tablas equipo_chat, equipo_tareas y equipo_notificaciones"""
    conexion = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_chat (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                es_fijado {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_tareas (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                creador_id INTEGER NOT NULL,
                asignado_a INTEGER,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                prioridad TEXT DEFAULT 'media',
                estado TEXT DEFAULT 'pendiente',
                completado_por_id INTEGER,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_completada TIMESTAMP,
                fecha_limite TIMESTAMP,
                FOREIGN KEY (creador_id) REFERENCES clientes(id),
                FOREIGN KEY (asignado_a) REFERENCES clientes(id),
                FOREIGN KEY (completado_por_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        # Migración de la columna fecha_limite si no existe
        try:
            if is_postgres:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='equipo_tareas'")
                cols = [r[0] for r in cursor.fetchall()]
                if 'fecha_limite' not in cols:
                    cursor.execute("ALTER TABLE equipo_tareas ADD COLUMN fecha_limite TIMESTAMP")
            else:
                cursor.execute("PRAGMA table_info(equipo_tareas)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'fecha_limite' not in cols:
                    cursor.execute("ALTER TABLE equipo_tareas ADD COLUMN fecha_limite TIMESTAMP")
        except Exception as err_col:
            print(f"[WARN] Error verificando columna fecha_limite: {err_col}")

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_notificaciones (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER NOT NULL,
                mensaje TEXT NOT NULL,
                tipo TEXT DEFAULT 'tarea_completada',
                leido {"BOOLEAN DEFAULT FALSE" if is_postgres else "BOOLEAN DEFAULT 0"},
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_invitaciones (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                admin_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                tipo_expiracion TEXT DEFAULT 'uso_unico',
                usos_restantes INTEGER DEFAULT 1,
                fecha_expiracion TIMESTAMP,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS equipo_solicitudes (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                admin_id INTEGER NOT NULL,
                empleado_id INTEGER NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES clientes(id),
                FOREIGN KEY (empleado_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')

        if is_postgres:
            tablas_rls = ['equipo_chat', 'equipo_tareas', 'equipo_notificaciones', 'equipo_invitaciones', 'equipo_solicitudes']
            for tbl in tablas_rls:
                try:
                    cursor.execute(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY;")
                except Exception as err_rls:
                    print(f"[WARN] No se pudo habilitar RLS en {tbl}: {err_rls}")

        conexion.commit()
    except Exception as e:
        print(f"[ERROR] Error al migrar tablas de equipo: {e}")
        if conexion:
            try:
                conexion.rollback()
            except Exception:
                pass
    finally:
        if conexion:
            try:
                conexion.close()
            except Exception:
                pass


def migrar_columnas_nuevas_clientes():
    """Agrega nuevas columnas a la tabla clientes si no existen."""
    conexion = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        is_postgres = bool(
            not os.environ.get('TESTING_DB') and
            os.environ.get('DATABASE_URL') and
            os.environ.get('DATABASE_URL').startswith('postgres')
        )

        
        if is_postgres:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clientes'")
            rows = cursor.fetchall()
            columnas_existentes = []
            for col in rows:
                if isinstance(col, (dict, list, tuple)):
                    columnas_existentes.append(col[0])
                else:
                    columnas_existentes.append(getattr(col, 'column_name', col[0]))
            
            if 'ultima_conexion' not in columnas_existentes:
                print("[INFO] Agregando columna ultima_conexion en Postgres...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN ultima_conexion TIMESTAMP")
                conexion.commit()
                
            if 'fecha_vencimiento_suscripcion' not in columnas_existentes:
                print("[INFO] Agregando columna fecha_vencimiento_suscripcion en Postgres...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN fecha_vencimiento_suscripcion TIMESTAMP")
                conexion.commit()

            if 'session_token' not in columnas_existentes:
                print("[INFO] Agregando columna session_token en Postgres...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN session_token TEXT")
                conexion.commit()

            if 'empresa_nombre' not in columnas_existentes:
                print("[INFO] Agregando columna empresa_nombre en Postgres...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN empresa_nombre TEXT")
                conexion.commit()

            if 'cotizaciones_trial_usadas' not in columnas_existentes:
                print("[INFO] Agregando columna cotizaciones_trial_usadas en Postgres...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN cotizaciones_trial_usadas INTEGER DEFAULT 0")
                conexion.commit()
        else:
            cursor.execute("PRAGMA table_info(clientes)")
            columnas = [col[1] for col in cursor.fetchall()]
            
            if 'ultima_conexion' not in columnas:
                print("[INFO] Agregando columna ultima_conexion en SQLite...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN ultima_conexion TIMESTAMP")
                
            if 'fecha_vencimiento_suscripcion' not in columnas:
                print("[INFO] Agregando columna fecha_vencimiento_suscripcion en SQLite...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN fecha_vencimiento_suscripcion TIMESTAMP")

            if 'session_token' not in columnas:
                print("[INFO] Agregando columna session_token en SQLite...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN session_token TEXT")

            if 'empresa_nombre' not in columnas:
                print("[INFO] Agregando columna empresa_nombre en SQLite...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN empresa_nombre TEXT")

            if 'cotizaciones_trial_usadas' not in columnas:
                print("[INFO] Agregando columna cotizaciones_trial_usadas en SQLite...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN cotizaciones_trial_usadas INTEGER DEFAULT 0")

            conexion.commit()
    except Exception as e:
        print(f"[ERROR] Error al migrar columnas de clientes: {e}")
        if conexion:
            try:
                conexion.rollback()
            except Exception:
                pass
    finally:
        if conexion:
            try:
                conexion.close()
            except Exception:
                pass


# =============================================
# FUNCIONES DE CONFIGURACIÓN DE PDF ("MI PDF")
# =============================================

def asegurar_tabla_configuracion_pdf(cursor):
    """Crea la tabla configuracion_pdf si no existe en la base de datos (SQLite y PostgreSQL)"""
    is_postgres = bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))
    try:
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS configuracion_pdf (
                id {"SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"},
                usuario_id INTEGER UNIQUE,
                tipo_hoja TEXT DEFAULT 'A4',
                color_tema TEXT DEFAULT '#dc2626',
                titulo_documento TEXT DEFAULT 'COTIZACIÓN DE VENTAS',
                empresa_nombre TEXT DEFAULT '',
                nit_emisor TEXT DEFAULT '',
                telefono TEXT DEFAULT '',
                correo TEXT DEFAULT '',
                direccion TEXT DEFAULT '',
                terminos_condiciones TEXT DEFAULT '1. Validez de la oferta: 15 días.\n2. Precios incluyen impuestos de ley.\n3. Tiempo de entrega a convenir.',
                nota_pie TEXT DEFAULT '¡Gracias por su preferencia!',
                responsable_nombre TEXT DEFAULT '',
                responsable_telefono TEXT DEFAULT '',
                responsable_email TEXT DEFAULT '',
                plazo_entrega TEXT DEFAULT '',
                logo_base64 TEXT DEFAULT '',
                logo_path TEXT DEFAULT '',
                firma_path TEXT DEFAULT '',
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES clientes(id)
            ){";" if is_postgres else ""}
        ''')
    except Exception as e:
        print(f"Error asegurando tabla configuracion_pdf: {e}")

def obtener_configuracion_pdf(usuario_id):
    """Obtiene la configuración de PDF para un usuario o retorna valores por defecto"""
    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            asegurar_tabla_configuracion_pdf(cursor)
            conexion.commit()

            cursor.execute("SELECT * FROM configuracion_pdf WHERE usuario_id = ?", (usuario_id,))
            row = cursor.fetchone()
            if row:
                col_names = [col[0] for col in cursor.description]
                res = dict(zip(col_names, row))
                if not res.get('responsable_nombre'):
                    cursor.execute("SELECT nombre, telefono, correo FROM clientes WHERE id = ?", (usuario_id,))
                    u = cursor.fetchone()
                    if u:
                        res['responsable_nombre'] = u[0] or 'Administrador'
                        res['responsable_telefono'] = res.get('responsable_telefono') or u[1] or ''
                        res['responsable_email'] = res.get('responsable_email') or u[2] or ''
                return res
    except Exception as e:
        print(f"Error obteniendo configuracion_pdf: {e}")
    
    return {
        'tipo_hoja': 'A4',
        'color_tema': '#dc2626',
        'titulo_documento': 'COTIZACIÓN DE VENTAS',
        'empresa_nombre': 'ELECTRORED BOLIVIA S.R.L.',
        'nit_emisor': '1029384021',
        'telefono': '+591 76543210',
        'correo': 'ventas@electrored.bo',
        'direccion': 'Av. Banzer Km 5.5 - Santa Cruz',
        'terminos_condiciones': '1. Validez de la oferta: 15 días.\n2. Precios incluyen impuestos de ley.\n3. Tiempo de entrega a convenir.',
        'nota_pie': '¡Gracias por su preferencia!',
        'responsable_nombre': 'Administrador',
        'responsable_telefono': '+591 76543210',
        'responsable_email': 'admin@sistema.com',
        'plazo_entrega': 'De acuerdo a la existencia / 48 horas',
        'logo_base64': '',
        'logo_path': '',
        'firma_path': ''
    }

def guardar_configuracion_pdf(usuario_id, datos):
    """Guarda o actualiza la configuración de PDF para un usuario"""
    try:
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            asegurar_tabla_configuracion_pdf(cursor)

            cursor.execute("SELECT COUNT(*) FROM configuracion_pdf WHERE usuario_id = ?", (usuario_id,))
            existe = cursor.fetchone()[0] > 0

            if existe:
                cursor.execute('''
                    UPDATE configuracion_pdf SET
                        tipo_hoja = ?,
                        color_tema = ?,
                        titulo_documento = ?,
                        empresa_nombre = ?,
                        nit_emisor = ?,
                        telefono = ?,
                        correo = ?,
                        direccion = ?,
                        terminos_condiciones = ?,
                        nota_pie = ?,
                        responsable_nombre = ?,
                        responsable_telefono = ?,
                        responsable_email = ?,
                        plazo_entrega = ?,
                        logo_base64 = ?,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE usuario_id = ?
                ''', (
                    datos.get('tipo_hoja', 'A4'),
                    datos.get('color_tema', '#dc2626'),
                    datos.get('titulo_documento', 'COTIZACIÓN DE VENTAS'),
                    datos.get('empresa_nombre', ''),
                    datos.get('nit_emisor', ''),
                    datos.get('telefono', ''),
                    datos.get('correo', ''),
                    datos.get('direccion', ''),
                    datos.get('terminos_condiciones', ''),
                    datos.get('nota_pie', ''),
                    datos.get('responsable_nombre', ''),
                    datos.get('responsable_telefono', ''),
                    datos.get('responsable_email', ''),
                    datos.get('plazo_entrega', ''),
                    datos.get('logo_base64', ''),
                    usuario_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO configuracion_pdf (
                        usuario_id, tipo_hoja, color_tema, titulo_documento,
                        empresa_nombre, nit_emisor, telefono, correo, direccion,
                        terminos_condiciones, nota_pie, responsable_nombre,
                        responsable_telefono, responsable_email, plazo_entrega, logo_base64
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    usuario_id,
                    datos.get('tipo_hoja', 'A4'),
                    datos.get('color_tema', '#dc2626'),
                    datos.get('titulo_documento', 'COTIZACIÓN DE VENTAS'),
                    datos.get('empresa_nombre', ''),
                    datos.get('nit_emisor', ''),
                    datos.get('telefono', ''),
                    datos.get('correo', ''),
                    datos.get('direccion', ''),
                    datos.get('terminos_condiciones', ''),
                    datos.get('nota_pie', ''),
                    datos.get('responsable_nombre', ''),
                    datos.get('responsable_telefono', ''),
                    datos.get('responsable_email', ''),
                    datos.get('plazo_entrega', ''),
                    datos.get('logo_base64', '')
                ))
            conexion.commit()
            return True
    except Exception as e:
        print(f"Error guardando configuracion_pdf: {e}")
        return False
