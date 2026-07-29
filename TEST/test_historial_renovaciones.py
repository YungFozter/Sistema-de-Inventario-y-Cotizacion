import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from db_wrapper import get_db_connection

def test_historial_renovaciones():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    print("--- INICIANDO TESTS DE HISTORIAL DE RENOVACIONES ---")
    
    with app.app_context():
        try:
            # 1. Autenticar como superadmin
            # Buscar un superadmin o crearlo
            conexion = get_db_connection()
            cursor = conexion.cursor()
            cursor.execute("SELECT id, correo, contrasena FROM clientes WHERE rol = 'superadmin' LIMIT 1")
            superadmin = cursor.fetchone()
            
            if not superadmin:
                cursor.execute("INSERT INTO clientes (nombre, correo, contrasena, rol) VALUES ('Super', 'super@test.com', 'scrypt:32768:8:1$mypasswordhash$somedata', 'superadmin')")
                conexion.commit()
                superadmin_id = cursor.lastrowid
                superadmin_email = 'super@test.com'
                superadmin_pass = 'admin123' # Just assuming, better to force session
            else:
                superadmin_id = superadmin[0]
                superadmin_email = superadmin[1]

            # Crear un admin para probar
            cursor.execute("INSERT INTO clientes (nombre, correo, contrasena, rol) VALUES ('Admin Test', 'admin_test_historial@test.com', 'scrypt:32768:8:1$mypasswordhash$somedata', 'admin')")
            conexion.commit()
            admin_id = cursor.lastrowid
            
            # Force login en la sesión
            with client.session_transaction() as sess:
                sess['user_id'] = superadmin_id
                sess['user_rol'] = 'superadmin'
                sess['logged_in'] = True
            
            # 2. Probar ruta de renovar_suscripcion
            print("1. Probando Renovar Suscripcion y guardar historial...")
            resp = client.post(f'/admin/renovar_suscripcion/{admin_id}', data={'dias': 90, 'notas': 'Pago por transferencia en test'})
            print(f"Resultado POST renovar: {resp.status_code}")
            
            # 3. Probar obtener historial
            print("2. Probando Obtener Historial de Renovaciones...")
            resp_hist = client.get(f'/admin/usuarios/{admin_id}/historial_renovaciones')
            print(f"Resultado GET historial: {resp_hist.status_code}")
            
            if resp_hist.status_code == 200:
                data = resp_hist.get_json()
                historial = data.get('historial', [])
                print(f"Registros en historial: {len(historial)}")
                if len(historial) > 0:
                    print(f"Último registro: +{historial[0]['dias_agregados']} días, Notas: {historial[0]['notas']}")
                else:
                    print("ERROR: No se guardó el registro en el historial.")
            else:
                print("ERROR: Falló el endpoint de obtener historial.")
                
            # Limpiar
            cursor.execute("DELETE FROM historial_renovaciones WHERE admin_id = ?", (admin_id,))
            cursor.execute("DELETE FROM clientes WHERE id = ?", (admin_id,))
            conexion.commit()
            
        except Exception as e:
            print(f"Excepción durante tests: {e}")
        finally:
            conexion.close()
            
    print("--- TESTS COMPLETADOS ---")

if __name__ == '__main__':
    test_historial_renovaciones()
