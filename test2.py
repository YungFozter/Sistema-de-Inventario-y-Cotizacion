import psycopg2
conn = psycopg2.connect('postgresql://postgres.bqtzkmjukbeiqftwxkdq:Cotizacion2026@aws-0-us-east-2.pooler.supabase.com:6543/postgres')
cursor = conn.cursor()
try:
    cursor.execute("SELECT id FROM clientes WHERE creador_id = %s AND codigo_cliente LIKE 'CLI-%'", (1,))
    print(cursor.fetchall())
except Exception as e:
    print("Error:", e)
