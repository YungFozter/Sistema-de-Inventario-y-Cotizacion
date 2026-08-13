import psycopg2
conn = psycopg2.connect('postgresql://postgres.bqtzkmjukbeiqftwxkdq:Cotizacion2026@aws-0-us-east-2.pooler.supabase.com:6543/postgres')
cursor = conn.cursor()
cursor.execute("SELECT id, codigo_cliente FROM clientes WHERE codigo_cliente = 'CLI-0001'")
print("CLI-0001:", cursor.fetchall())
cursor.execute("SELECT id, codigo_cliente, nombre FROM clientes WHERE codigo_cliente = 'CLI-0000'")
print("CLI-0000:", cursor.fetchall())
cursor.execute("SELECT id, codigo_cliente, nombre FROM clientes ORDER BY id DESC LIMIT 5")
print("Last 5:", cursor.fetchall())
