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

def test_registro_flujo_otp(client):
    # Paso 1: Enviar código OTP
    payload_envio = {
        'nombre': 'Nuevo Test OTP',
        'empresa_nombre': 'Test Company',
        'correo': 'nuevo_otp@test.com',
        'telefono': '77123456',
        'contrasena': 'test1234',
        'confirmar_contrasena': 'test1234'
    }
    resp1 = client.post('/registro/enviar-codigo', json=payload_envio)
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1.get('ok') is True

    # Obtener el código de la sesión de prueba
    with client.session_transaction() as sess:
        pending = sess.get('pending_registro')
        assert pending is not None
        codigo_otp = pending['codigo']

    # Paso 2: Verificar código OTP correcto
    resp2 = client.post('/registro/verificar-codigo', json={'codigo': codigo_otp})
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2.get('ok') is True
    assert '/login' in data2.get('redirect', '')


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
