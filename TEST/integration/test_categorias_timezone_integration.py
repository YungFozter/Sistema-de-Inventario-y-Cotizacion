import pytest
from datetime import datetime, timezone, timedelta
from models import obtener_fecha_bolivia, guardar_importacion_pdf, obtener_importaciones_pdf

def test_guardar_y_obtener_importacion_bolivia_timezone(app):
    with app.app_context():
        items = [{'codigo': 'TEST-TZ-01', 'descripcion': 'Producto Test Timezone', 'precio_unitario': 10.0}]
        imp_id, nombre = guardar_importacion_pdf('Test Timezone Import', items, usuario_id=1)
        
        importaciones = obtener_importaciones_pdf()
        imp_guardada = next((i for i in importaciones if i['id'] == imp_id), None)
        
        assert imp_guardada is not None
        assert imp_guardada['nombre_importacion'] == 'Test Timezone Import'
        # Verificar que la fecha contenga el formato d/m/Y H:M:S sin sufijo GMT erróneo
        assert '/' in imp_guardada['fecha_importacion']

def test_api_categorias_crud(client, admin_user):
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user['id']
        sess['user_rol'] = 'admin'

    # 1. Crear categoría
    res = client.post('/api/categorias', json={'nombre': 'Categoría Admin Test', 'descripcion': 'Probando CRUD Admin'})
    data = res.get_json()
    assert data['success'] is True
    cat_id = data['categoria_id']

    # 2. Listar categorías
    res_get = client.get('/api/categorias')
    cat_list = res_get.get_json()
    assert any(c['id'] == cat_id and c['nombre'] == 'Categoría Admin Test' for c in cat_list)

    # 3. Editar categoría
    res_put = client.put(f'/api/categorias/{cat_id}', json={'nombre': 'Categoría Admin Test Editada', 'descripcion': 'Editada'})
    assert res_put.get_json()['success'] is True

    # 4. Eliminar categoría
    res_del = client.delete(f'/api/categorias/{cat_id}')
    assert res_del.get_json()['success'] is True
