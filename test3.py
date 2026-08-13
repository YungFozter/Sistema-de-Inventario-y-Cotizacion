from db_wrapper import get_db_connection
from dotenv import load_dotenv
import os

load_dotenv()
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, codigo_cliente FROM clientes WHERE codigo_cliente = 'CLI-0001' OR codigo_cliente = 'COD-001'")
    print("MATCHES:", cursor.fetchall())
    
    # Also check what generar_codigo_cliente_unico does
    from routes.clientes import generar_codigo_cliente_unico
    print("NEXT CODE:", generar_codigo_cliente_unico(cursor, 1))
except Exception as e:
    print("ERR:", e)
