import pytest
from datetime import datetime, timezone, timedelta
from db_wrapper import get_db_connection

def test_flujo_e2e_generacion_y_uso_pin_suscripcion(client, superadmin_user):
    """
    Flujo E2E del modelo freemium:
    1. Superadmin genera y elimina PINs
    2. Usuario se registra GRATIS (sin PIN) → recibe rol 'admin' con trial
    3. Superadmin genera un PIN de suscripción
    4. Admin activa su PIN via /suscripcion/activar-pin
    5. Verificar PIN quemado correctamente
    6. Re-uso del PIN es rechazado
    """
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
    # PASO 2: Usuario anónimo se registra GRATIS (modelo freemium, sin PIN)
    # =========================================================================
    client.get('/logout', follow_redirects=True)

    nombre_nuevo_admin = "Admin E2E Negocio"
    email_nuevo_admin = "nuevo_admin_e2e@test.com"
    empresa_nuevo_admin = "Empresa Prueba E2E S.R.L."

    payload_registro = {
        'nombre': nombre_nuevo_admin,
        'empresa_nombre': empresa_nuevo_admin,
        'correo': email_nuevo_admin,
        'telefono': '77123456',
        'contrasena': 'Password123!',
        'confirmar_contrasena': 'Password123!',
    }

    res_reg = client.post('/registro', data=payload_registro, follow_redirects=True)
    assert res_reg.status_code == 200


    # =========================================================================
    # PASO 3: Verificar que el usuario es admin freemium (sin suscripción)
    # =========================================================================
    conexion = get_db_connection()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT id, rol, empresa_nombre, fecha_vencimiento_suscripcion, cotizaciones_trial_usadas FROM clientes WHERE correo = ?",
        (email_nuevo_admin,)
    )
    nuevo_admin_row = cursor.fetchone()
    conexion.close()

    assert nuevo_admin_row is not None
    nuevo_admin_id = nuevo_admin_row[0]
    assert nuevo_admin_row[1] == 'admin'                       # Siempre crea admin
    assert nuevo_admin_row[2] == empresa_nuevo_admin           # empresa_nombre guardado
    assert nuevo_admin_row[3] is None                         # Sin suscripción activa (trial)
    assert (nuevo_admin_row[4] or 0) == 0                     # Trial recién empezado

    # =========================================================================
    # PASO 4: Superadmin genera un PIN para este nuevo admin
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = superadmin_user['id']
        sess['user_email'] = superadmin_user['email']
        sess['user_rol'] = 'superadmin'
        sess['user_nombre'] = 'Superadmin Test'

    res_gen = client.post('/admin/pines', follow_redirects=True)
    assert res_gen.status_code == 200

    conexion = get_db_connection()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, pin, usado, usado_por FROM pines_admin ORDER BY id DESC LIMIT 1")
    pin_row = cursor.fetchone()
    conexion.close()

    assert pin_row is not None
    pin_id   = pin_row[0]
    pin_code = pin_row[1]
    assert pin_row[2] == 0 or pin_row[2] is False   # Estado inicial: Disponible
    assert pin_row[3] is None                        # Nadie lo ha usado aún

    # =========================================================================
    # PASO 5: Admin activa su suscripción via /suscripcion/activar-pin (JSON)
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = nuevo_admin_id
        sess['user_email'] = email_nuevo_admin
        sess['user_rol'] = 'admin'
        sess['user_nombre'] = nombre_nuevo_admin
        sess['trial_activo'] = True
        sess['trial_usadas'] = 0

    res_activar = client.post(
        '/suscripcion/activar-pin',
        json={'pin': pin_code},
        content_type='application/json'
    )
    assert res_activar.status_code == 200
    data_activar = res_activar.get_json()
    assert data_activar.get('ok') is True

    # =========================================================================
    # PASO 6: Verificar que el PIN quedó quemado y la suscripción está activa
    # =========================================================================
    conexion = get_db_connection()
    cursor = conexion.cursor()

    cursor.execute("SELECT usado, usado_por FROM pines_admin WHERE id = ?", (pin_id,))
    pin_actualizado = cursor.fetchone()

    cursor.execute("SELECT fecha_vencimiento_suscripcion FROM clientes WHERE id = ?", (nuevo_admin_id,))
    admin_actualizado = cursor.fetchone()
    conexion.close()

    assert pin_actualizado[0] == 1 or pin_actualizado[0] is True    # PIN marcado como QUEMADO
    assert pin_actualizado[1] == nuevo_admin_id                      # usado_por correcto
    assert admin_actualizado[0] is not None                          # Tiene fecha de vencimiento

    # =========================================================================
    # PASO 7: Superadmin verifica la vista /admin/pines (ningún "None" suelto)
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = superadmin_user['id']
        sess['user_email'] = superadmin_user['email']
        sess['user_rol'] = 'superadmin'

    res_vista_pines = client.get('/admin/pines')
    assert res_vista_pines.status_code == 200
    html_pines = res_vista_pines.get_data(as_text=True)
    assert nombre_nuevo_admin in html_pines

    # =========================================================================
    # PASO 8: Intentar re-utilizar el MISMO PIN (Debe ser rechazado)
    # =========================================================================
    with client.session_transaction() as sess:
        sess['user_id'] = nuevo_admin_id
        sess['user_email'] = email_nuevo_admin
        sess['user_rol'] = 'admin'
        sess['trial_activo'] = False

    res_reintento = client.post(
        '/suscripcion/activar-pin',
        json={'pin': pin_code},
        content_type='application/json'
    )
    assert res_reintento.status_code == 400
    data_reintento = res_reintento.get_json()
    assert data_reintento.get('ok') is False
    assert 'inválido' in (data_reintento.get('msg') or '').lower() or \
           'utilizado' in (data_reintento.get('msg') or '').lower()
