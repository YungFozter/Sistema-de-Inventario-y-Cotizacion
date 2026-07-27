import sqlite3
import psycopg2
import os
import json
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Rutas y Conexiones
SQLITE_DB_PATH = r"C:\Users\iOs\Downloads\db.sqlite3"
POSTGRES_URL = "postgresql://postgres.bqtzkmjukbeiqftwxkdq:Cotizacion2026@aws-0-us-east-2.pooler.supabase.com:6543/postgres"

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def migrate():
    print("Iniciando proceso de migración de datos...")
    
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"ERROR: No se encontró el archivo SQLite en {SQLITE_DB_PATH}")
        return

    # Conectar a SQLite
    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        sqlite_conn.row_factory = dict_factory
        sqlite_cursor = sqlite_conn.cursor()
        print(f"[OK] Conectado a SQLite: {SQLITE_DB_PATH}")
    except Exception as e:
        print(f"Error conectando a SQLite: {e}")
        return

    # Conectar a PostgreSQL
    try:
        pg_conn = psycopg2.connect(POSTGRES_URL)
        pg_cursor = pg_conn.cursor()
        print("[OK] Conectado a PostgreSQL en Supabase")
    except Exception as e:
        print(f"Error conectando a PostgreSQL: {e}")
        sqlite_conn.close()
        return

    # Definir el orden correcto de las tablas por las llaves foráneas
    tablas = [
        "categorias",
        "clientes",
        "productos",
        "cotizaciones",
        "cotizacion_productos",
        "importaciones_pdf",
        "items_importados_temp",
        "logs"
    ]

    try:
        # Conjuntos para almacenar IDs válidos de las tablas principales
        valid_ids = {
            'categorias': set(),
            'clientes': set(),
            'productos': set(),
            'cotizaciones': set(),
            'importaciones_pdf': set()
        }

        for tabla in tablas:
            # Leer registros de SQLite
            try:
                sqlite_cursor.execute(f"SELECT * FROM {tabla}")
                filas = sqlite_cursor.fetchall()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    print(f"[WARNING] La tabla '{tabla}' no existe en la base de datos local. Omitiendo...")
                    continue
                else:
                    raise e
            
            if not filas:
                print(f"[INFO] Tabla '{tabla}' vacía, omitiendo...")
                continue
                
            print(f"[INFO] Migrando tabla '{tabla}' ({len(filas)} registros)...")
            
            columnas = list(filas[0].keys())
            columnas_str = ", ".join(columnas)
            placeholders = ", ".join(["%s"] * len(columnas))
            insert_query = f"INSERT INTO {tabla} ({columnas_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING;"
            
            valores_batch = []
            for fila in filas:
                # Si esta tabla es una de las principales, guardar su ID
                if tabla in valid_ids and 'id' in fila:
                    valid_ids[tabla].add(fila['id'])

                valores = []
                for col in columnas:
                    val = fila[col]
                    
                    if val == "":
                        val = None
                        
                    if tabla == 'clientes' and col == 'activo':
                        val = bool(val) if val is not None else True
                    if tabla == 'categorias' and col == 'activo':
                        val = bool(val) if val is not None else True
                    if tabla == 'items_importados_temp' and col == 'registrado':
                        val = bool(val) if val is not None else False
                        
                    # Reparar llaves foráneas rotas
                    if tabla == 'productos' and col == 'categoria_id' and val is not None:
                        if val not in valid_ids['categorias']:
                            val = None
                    if tabla == 'cotizaciones':
                        if col == 'cliente_id' and val is not None and val not in valid_ids['clientes']:
                            val = None
                        if col == 'creador_id' and val is not None and val not in valid_ids['clientes']:
                            val = None
                    if tabla == 'cotizacion_productos':
                        if col == 'cotizacion_id' and val is not None and val not in valid_ids['cotizaciones']:
                            val = None
                        if col == 'producto_id' and val is not None and val not in valid_ids['productos']:
                            val = None
                    if tabla == 'importaciones_pdf' and col == 'usuario_id' and val is not None:
                        if val not in valid_ids['clientes']:
                            val = None
                    if tabla == 'items_importados_temp':
                        if col == 'importacion_id' and val is not None and val not in valid_ids['importaciones_pdf']:
                            val = None
                        if col == 'producto_registrado_id' and val is not None and val not in valid_ids['productos']:
                            val = None
                    if tabla == 'logs' and col == 'usuario_id' and val is not None:
                        if val not in valid_ids['clientes']:
                            val = None
                    
                    valores.append(val)
                valores_batch.append(tuple(valores))
                
            execute_batch(pg_cursor, insert_query, valores_batch)
            print(f"[OK] Insertados {len(valores_batch)} registros en '{tabla}'.")
            
            # Actualizar secuencias de PostgreSQL para que no choquen futuros inserts
            try:
                pg_cursor.execute(f"SELECT setval('{tabla}_id_seq', (SELECT MAX(id) FROM {tabla}));")
            except Exception as seq_err:
                # Si falla la secuencia no detenemos el proceso, puede que la tabla no use seq
                pg_conn.rollback()
                pass
            else:
                pg_conn.commit()

        # Commit final
        pg_conn.commit()
        print("\n🎉 ¡MIGRACIÓN COMPLETADA CON ÉXITO! 🎉")
        print("Tus clientes, productos y cotizaciones ahora están en la nube.")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[ERROR CRÍTICO] Ocurrió un error durante la migración: {e}")
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == '__main__':
    migrate()
