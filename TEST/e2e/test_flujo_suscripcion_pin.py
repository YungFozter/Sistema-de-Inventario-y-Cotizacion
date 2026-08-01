import pytest
from datetime import datetime, timezone, timedelta
from db_wrapper import get_db_connection

def test_flujo_e2e_generacion_y_uso_pin_suscripcion(client, superadmin_user):
    # =========================================================================
    # PASO 1: Iniciar sesión como Superadmin y probar eliminación de PIN
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = superadmin_user['id']
        sess['user_email'] = superadmin_user['email']
        sess['user_rol'] = 'superadmin'
        sess['user_nombre'] = 'Superadmin Test'

    # 1.1 Generar un PIN para probar eliminación
    res_gen_del = client.post('/admin/pines', follow_redirects=True)
    assert res_gen_del.status_code == 200

    conexion = get_db_connection()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, pin FROM pines_admin ORDER BY id DESC LIMIT 1")
    pin_borrar_row = cursor.fetchone()
    conexion.close()
    
    assert pin_borrar_row is not None
    pin_borrar_id = pin_borrar_row[0]
    pin_borrar_code = pin_borrar_row[1]

    # 1.2 Eliminar el PIN mediante POST /admin/pines/eliminar/<id>
    res_del = client.post(f'/admin/pines/eliminar/{pin_borrar_id}', follow_redirects=True)
    assert res_del.status_code == 200
    assert "PIN eliminado exitosamente" in res_del.get_data(as_text=True)

    conexion = get_db_connection()
    cursor = conexion.cursor()
    cursor.execute("SELECT id FROM pines_admin WHERE id = ?", (pin_borrar_id,))
    assert cursor.fetchone() is None  # Confirmar que fue eliminado de la BD
    conexion.close()

    # =========================================================================
    # PASO 2: Generar un nuevo PIN válido para el registro de Admin
    # =========================================================================
    res_gen = client.post('/admin/pines', follow_redirects=True)
    assert res_gen.status_code == 200

    conexion = get_db_connection()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, pin, usado, creado_en, usado_por FROM pines_admin ORDER BY id DESC LIMIT 1")
    pin_row = cursor.fetchone()
    conexion.close()

    assert pin_row is not None
    pin_id = pin_row[0]
    pin_code = pin_row[1]
    assert pin_row[2] == 0 or pin_row[2] is False  # Estado inicial: Disponible
    assert pin_row[4] is None                     # Nadie lo ha usado aún

    # =========================================================================
    # PASO 3: Usuario anónimo se registra como Admin usando el PIN
    # =========================================================================
    client.get('/logout', follow_redirects=True)

    nombre_nuevo_admin = "Admin E2E Negocio"
    email_nuevo_admin = "nuevo_admin_e2e@test.com"
    payload_registro = {
        'nombre': nombre_nuevo_admin,
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
    # PASO 4: Verificación del estado del PIN y la asignación Usado Por
    # =========================================================================
    conexion = get_db_connection()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, rol, fecha_vencimiento_suscripcion FROM clientes WHERE correo = ?", (email_nuevo_admin,))
    nuevo_admin_row = cursor.fetchone()
    assert nuevo_admin_row is not None
    nuevo_admin_id = nuevo_admin_row[0]

    # Verificar registro del PIN quemado y que usado_por NO SEA NULL
    cursor.execute("SELECT id, usado, usado_por FROM pines_admin WHERE id = ?", (pin_id,))
    pin_actualizado = cursor.fetchone()
    conexion.close()

    assert pin_actualizado[1] == 1 or pin_actualizado[1] is True  # Marcado como QUEMADO
    assert pin_actualizado[2] == nuevo_admin_id                   # ID del nuevo Admin (No None)

    # =========================================================================
    # PASO 5: Iniciar sesión como Superadmin y verificar vista HTML (/admin/pines)
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = superadmin_user['id']
        sess['user_email'] = superadmin_user['email']
        sess['user_rol'] = 'superadmin'

    res_vista_pines = client.get('/admin/pines')
    assert res_vista_pines.status_code == 200
    html_pines = res_vista_pines.get_data(as_text=True)

    # Verificar que aparezca el nombre del usuario que lo usó y NO aparezca "None"
    assert nombre_nuevo_admin in html_pines
    assert "None" not in html_pines

    # =========================================================================
    # PASO 6: Intentar re-utilizar el MISMO PIN (Debe ser rechazado)
    # =========================================================================
    client.get('/logout', follow_redirects=True)

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
    assert "PIN inválido o ya utilizado" in res_reintento.get_data(as_text=True)
