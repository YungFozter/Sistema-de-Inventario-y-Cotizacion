import os
import pytest
from db_wrapper import get_db_connection
from utils.backup import listar_backups, get_backup_dir

def test_acceso_respaldos_requiere_login(client):
    resp = client.get('/admin/respaldos')
    assert resp.status_code == 302

def test_acceso_respaldos_restringido_para_admin(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})
    resp = client.get('/admin/respaldos')
    # superadmin_required redirects or blocks non-superadmins
    assert resp.status_code in (302, 403)

def test_flujo_completo_respaldos(client, superadmin_user, monkeypatch, tmp_path):
    # Usar un directorio temporal para respaldos en este test
    backup_dir = str(tmp_path / "test_backups")
    monkeypatch.setenv("BACKUP_DIR", backup_dir)

    # 1. Login Superadmin
    resp_login = client.post('/login', data={'correo': superadmin_user['email'], 'contrasena': superadmin_user['password']})
    assert resp_login.status_code == 302

    # 2. Cargar vista de respaldos (inicialmente vacía)
    resp = client.get('/admin/respaldos')
    assert resp.status_code == 200
    assert b'No hay respaldos guardados' in resp.data or b'0 MB' in resp.data

    # 3. Crear Respaldo
    resp_crear = client.post('/admin/respaldos/crear')
    assert resp_crear.status_code == 302

    # Verificar que el respaldo fue creado
    backups = listar_backups()
    assert len(backups) == 1
    filename = backups[0]['filename']

    # 4. Cargar vista y verificar que aparece el archivo
    resp_list = client.get('/admin/respaldos')
    assert resp_list.status_code == 200
    assert filename.encode('utf-8') in resp_list.data

    # 5. Descargar Respaldo
    resp_descarga = client.get(f'/admin/respaldos/descargar/{filename}')
    assert resp_descarga.status_code == 200
    assert 'attachment' in resp_descarga.headers.get('Content-Disposition', '')
    resp_descarga.close()

    # 6. Restaurar Respaldo
    resp_restaurar = client.post(f'/admin/respaldos/restaurar/{filename}')
    assert resp_restaurar.status_code == 302
    # Debe haberse creado un auto-backup preventivo
    backups_after_restore = listar_backups()
    assert len(backups_after_restore) == 2

    # 7. Eliminar Respaldo
    resp_eliminar = client.post(f'/admin/respaldos/eliminar/{filename}')
    assert resp_eliminar.status_code == 302
    backups_final = listar_backups()
    assert len(backups_final) == 1
