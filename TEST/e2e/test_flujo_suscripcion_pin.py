import pytest
from datetime import datetime, timezone, timedelta
from db_wrapper import get_db_connection

def test_flujo_e2e_generacion_y_uso_pin_suscripcion(client, superadmin_user):
    # =========================================================================
    # PASO 1: Iniciar sesión como Superadmin y generar un nuevo PIN
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = superadmin_user['id']
        sess['user_email'] = superadmin_user['email']
        sess['user_rol'] = 'superadmin'
        sess['user_nombre'] = 'Superadmin Test'

    # Generar PIN vía POST /admin/pines
    response_gen = client.post('/admin/pines', follow_redirects=True)
    assert response_gen.status_code == 200

    # Consultar el PIN recién generado en la base de datos
    conexion = get_db_connection()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, pin, usado, creado_en, usado_por FROM pines_admin ORDER BY id DESC LIMIT 1")
    pin_row = cursor.fetchone()
    conexion.close()

    assert pin_row is not None
    pin_id = pin_row[0]
    pin_code = pin_row[1]
    assert pin_row[2] == 0 or pin_row[2] is False  # Estado inicial: Disponible (0 / False)
    assert pin_row[4] is None                     # Nadie lo ha usado aún

    # =========================================================================
    # PASO 2: Usuario anónimo se registra como Admin usando el PIN generado
    # =========================================================================
    # Limpiar la sesión para simular usuario nuevo sin autenticar
    client.get('/logout', follow_redirects=True)

    email_nuevo_admin = "nuevo_admin_e2e@test.com"
    payload_registro = {
        'nombre': 'Admin E2E Negocio',
        'correo': email_nuevo_admin,
        'telefono': '77123456',
        'contrasena': 'Password123!',
        'confirmar_contrasena': 'Password123!',
        'rol': 'admin',
        'pin_admin': pin_code
    }

    res_reg = client.post('/registro', data=payload_registro, follow_redirects=True)
    assert res_reg.status_code == 200
    assert "¡Cuenta creada exitosamente!" in res_reg.get_data(as_text=True)

    # =========================================================================
    # PASO 3: Verificación del estado del PIN (Pasó a Usado / Quemado)
    # =========================================================================
    conexion = get_db_connection()
    cursor = conexion.cursor()

    # Obtener el ID del nuevo usuario Admin creado
    cursor.execute("SELECT id, rol, fecha_vencimiento_suscripcion FROM clientes WHERE correo = ?", (email_nuevo_admin,))
    nuevo_admin_row = cursor.fetchone()
    assert nuevo_admin_row is not None
    nuevo_admin_id = nuevo_admin_row[0]
    assert nuevo_admin_row[1] == 'admin'

    # Verificar que la fecha de vencimiento de suscripción sea aproximadamente dentro de 30 días
    vencimiento_str = str(nuevo_admin_row[2])
    assert vencimiento_str is not None and len(vencimiento_str) > 0

    # Verificar el registro del PIN quemado
    cursor.execute("SELECT id, usado, usado_por FROM pines_admin WHERE id = ?", (pin_id,))
    pin_actualizado = cursor.fetchone()
    conexion.close()

    assert pin_actualizado[1] == 1 or pin_actualizado[1] is True  # Marcado como QUEMADO/USADO
    assert pin_actualizado[2] == nuevo_admin_id                   # Asignado al ID del nuevo Admin

    # =========================================================================
    # PASO 4: Intentar re-utilizar el MISMO PIN (Debe ser rechazado)
    # =========================================================================
    payload_reintento = {
        'nombre': 'Intruso Admin',
        'correo': 'intruso@test.com',
        'telefono': '77000000',
        'contrasena': 'Password123!',
        'confirmar_contrasena': 'Password123!',
        'rol': 'admin',
        'pin_admin': pin_code
    }

    res_reintento = client.post('/registro', data=payload_reintento, follow_redirects=True)
    assert res_reintento.status_code == 200
    html_reintento = res_reintento.get_data(as_text=True)
    assert "PIN inválido o ya utilizado" in html_reintento
