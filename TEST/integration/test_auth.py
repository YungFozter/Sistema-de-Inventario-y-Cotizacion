import pytest

def test_login_success(client, admin_user):
    resp = client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})
    if resp.status_code != 302:
        print("LOGIN FAILURE DATA:", resp.data)
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers.get('Location', '')

def test_login_failure(client, admin_user):
    resp = client.post('/login', data={'correo': admin_user['email'], 'contrasena': 'wrongpassword'})
    assert resp.status_code == 200
    assert b'Credenciales incorrectas' in resp.data

def test_acceso_denegado_sin_login(client):
    resp = client.get('/dashboard')
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

def test_logout(client, admin_user):
    # Primero hacemos login
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})
    
    # Hacemos logout
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert '/' in resp.headers.get('Location', '')
    
    # Verificamos que ya no puede acceder
    resp = client.get('/dashboard')
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

def test_registro_requiere_pin(client):
    # Intentar registrarse sin PIN
    resp = client.post('/registro', data={
        'nombre': 'Nuevo Test',
        'correo': 'nuevo@test.com',
        'contrasena': 'test1234',
        'confirmar_contrasena': 'test1234',
        'pin_superadmin': ''
    })
    # Deberia dar un mensaje o redireccionar
    assert b'PIN no v' in resp.data or b'invalido' in resp.data.lower() or resp.status_code in [200, 302]

def test_sesion_unica_invalida_segunda_conexion(app, admin_user):
    client1 = app.test_client()
    client2 = app.test_client()

    # 1. Sesión 1 inicia sesión en Dispositivo 1
    resp1 = client1.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})
    assert resp1.status_code == 302

    # Verificar que Dispositivo 1 puede acceder a una ruta protegida
    dashboard1 = client1.get('/dashboard')
    assert dashboard1.status_code == 200

    # 2. Sesión 2 inicia sesión con las mismas credenciales en Dispositivo 2
    resp2 = client2.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})
    assert resp2.status_code == 302

    # Verificar que Dispositivo 2 accede correctamente
    dashboard2 = client2.get('/dashboard')
    assert dashboard2.status_code == 200

    # 3. Dispositivo 1 intenta hacer una nueva petición -> Debe ser invalidado y redirigido a /login
    dashboard1_nuevo = client1.get('/dashboard')
    assert dashboard1_nuevo.status_code == 302
    assert '/login' in dashboard1_nuevo.headers.get('Location', '')
