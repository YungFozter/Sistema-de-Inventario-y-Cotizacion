import pytest
from db_wrapper import get_db_connection

def test_listar_clientes_requiere_login(client):
    resp = client.get('/clientes')
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

def test_crud_cliente(client, admin_user):
    # 1. Login
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # 2. Crear Cliente
    resp_crear = client.post('/clientes', data={
        'razon_social': 'Cliente Test Integracion',
        'nit': '123456-7',
        'telefono': '123456789',
        'referencia': 'Ref Test',
        'tipo_cliente': 'normal'
    })
    assert resp_crear.status_code == 302 # Redirect to /clientes
    
    # Verify in DB
    conn = get_db_connection()
    c = conn.execute("SELECT id FROM clientes WHERE nombre = ?", ('Cliente Test Integracion',)).fetchone()
    assert c is not None
    cliente_id = c['id']
    conn.close()

    # 3. Listar Clientes
    resp_listar = client.get('/clientes')
    assert resp_listar.status_code == 200
    assert b'Cliente Test Integracion' in resp_listar.data

    # 4. Editar Cliente
    resp_editar = client.post(f'/clientes/editar/{cliente_id}', data={
        'nombre': 'Cliente Editado',
        'nit': '765432-1',
        'telefono': '987654321',
        'referencia': 'Ref Edit',
        'tipo_cliente': 'frecuente'
    })
    assert resp_editar.status_code == 302
    
    resp_listar = client.get('/clientes')
    assert b'Cliente Editado' in resp_listar.data
    assert b'765432-1' in resp_listar.data

    # 5. Eliminar Cliente
    resp_eliminar = client.get(f'/clientes/eliminar/{cliente_id}')
    assert resp_eliminar.status_code == 302
    
    resp_listar2 = client.get('/clientes')
    assert b'Cliente Editado' not in resp_listar2.data

def test_codigo_cliente_sin_saltos_ni_duplicados(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # Crear 3 clientes nuevos para probar la secuencia
    client.post('/clientes', data={'razon_social': 'Cliente Seq 1', 'telefono': '70000000'})
    client.post('/clientes', data={'razon_social': 'Cliente Seq 2', 'telefono': '70000000'})
    client.post('/clientes', data={'razon_social': 'Cliente Seq 3', 'telefono': '70000000'})

    conn = get_db_connection()
    c1 = conn.execute("SELECT codigo_cliente FROM clientes WHERE nombre = 'Cliente Seq 1'").fetchone()[0]
    c2 = conn.execute("SELECT codigo_cliente FROM clientes WHERE nombre = 'Cliente Seq 2'").fetchone()[0]
    c3 = conn.execute("SELECT codigo_cliente FROM clientes WHERE nombre = 'Cliente Seq 3'").fetchone()[0]
    
    num1 = int(c1.split('-')[1])
    num2 = int(c2.split('-')[1])
    num3 = int(c3.split('-')[1])
    
    assert num2 == num1 + 1
    assert num3 == num1 + 2

    # Eliminar Cliente 2 (crea hueco num2)
    id2 = conn.execute("SELECT id FROM clientes WHERE nombre = 'Cliente Seq 2'").fetchone()[0]
    conn.close()
    client.get(f'/clientes/eliminar/{id2}')

    # Crear Cliente 4 -> Debe rellenar el hueco num2 sin saltar números
    client.post('/clientes', data={'razon_social': 'Cliente GapFill', 'telefono': '70000000'})

    conn = get_db_connection()
    c4 = conn.execute("SELECT codigo_cliente FROM clientes WHERE nombre = 'Cliente GapFill'").fetchone()[0]
    num4 = int(c4.split('-')[1])
    assert num4 == num2
    conn.close()
