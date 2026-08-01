import pytest
from db_wrapper import get_db_connection

def test_crud_categorias(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # 1. Crear Categoría (CREATE)
    resp_crear = client.post('/api/categorias', json={
        'nombre': 'CatTestCRUD',
        'descripcion': 'DescInicial'
    })
    assert resp_crear.status_code == 200
    cat_id = resp_crear.get_json()['categoria_id']

    # 2. Obtener Categorías (READ)
    resp_listar = client.get('/api/categorias')
    assert resp_listar.status_code == 200
    data = resp_listar.get_json()
    assert any(c['id'] == cat_id and c['nombre'] == 'CatTestCRUD' for c in data)

    # 3. Editar Categoría (UPDATE)
    resp_editar = client.put(f'/api/categorias/{cat_id}', json={
        'nombre': 'CatTestEditada',
        'descripcion': 'DescActualizada'
    })
    assert resp_editar.status_code == 200
    assert resp_editar.get_json()['success'] is True

    # Verificar que se actualizó en la BD
    resp_listar2 = client.get('/api/categorias')
    assert resp_listar2.status_code == 200
    data2 = resp_listar2.get_json()
    assert any(c['id'] == cat_id and c['nombre'] == 'CatTestEditada' and c['descripcion'] == 'DescActualizada' for c in data2)

    # 4. Eliminar Categoría (DELETE)
    resp_eliminar = client.delete(f'/api/categorias/{cat_id}')
    assert resp_eliminar.status_code == 200
    assert resp_eliminar.get_json()['success'] is True

    # Verificar eliminación
    resp_listar3 = client.get('/api/categorias')
    assert not any(c['id'] == cat_id for c in resp_listar3.get_json())

def test_crud_productos(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # Crear Producto
    resp_crear = client.post('/productos', data={
        'empresa': 'Apple',
        'codigo': 'PROD-INT-UNIQUE',
        'descripcion': 'Producto Integracion',
        'marca': 'Marca Test',
        'tm': 'TM-1',
        'um': 'PZ',
        'cantidad': '10',
        'precio_unitario': '150.5'
    })
    assert resp_crear.status_code in (200, 302)
    
    conn = get_db_connection()
    prod = conn.execute("SELECT id FROM productos WHERE descripcion = ?", ('Producto Integracion',)).fetchone()
    assert prod is not None
    prod_id = prod['id']
    conn.close()

    # Listar Producto
    resp_listar = client.get('/productos')
    assert resp_listar.status_code == 200
    assert b'Producto Integracion' in resp_listar.data

    # Editar Producto
    resp_editar = client.post(f'/productos/editar/{prod_id}', data={
        'empresa': 'Samsung',
        'codigo': 'PROD-INT-UNIQUE',
        'descripcion': 'Prod Editado',
        'marca': 'Marca E',
        'tm': 'TM-1',
        'um': 'PZ',
        'cantidad': '10',
        'precio_unitario': '200'
    })
    assert resp_editar.status_code == 302
    
    resp_listar2 = client.get('/productos')
    assert b'Prod Editado' in resp_listar2.data

    # Eliminar Producto
    resp_eliminar = client.get(f'/productos/eliminar/{prod_id}')
    assert resp_eliminar.status_code == 302
    
    resp_listar3 = client.get('/productos')
    assert b'Prod Editado' not in resp_listar3.data

def test_registro_y_filtrado_completo_productos(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # 1. Crear una Categoría de prueba
    resp_cat = client.post('/api/categorias', json={'nombre': 'CatFiltroTest', 'descripcion': 'Cat Test'})
    assert resp_cat.status_code == 200
    cat_id = resp_cat.get_json()['categoria_id']

    # 2. Registrar Producto con datos únicos para filtrado
    resp_reg = client.post('/productos', data={
        'empresa': 'EmpresaAlfaFilter',
        'codigo': 'COD-FILTER-777',
        'descripcion': 'Laptop Gaming Extreme 777',
        'marca': 'MarcaOmegaFilter',
        'tm': 'TM-X',
        'um': 'PZ',
        'cantidad': '15',
        'precio_unitario': '1250.00',
        'categoria_id': str(cat_id)
    })
    assert resp_reg.status_code in (200, 302)

    # 3. Verificar que aparece en "Productos Registrados" (GET /productos)
    resp_vista = client.get('/productos?tab=registrados')
    assert resp_vista.status_code == 200
    assert b'Laptop Gaming Extreme 777' in resp_vista.data
    assert b'COD-FILTER-777' in resp_vista.data
    assert b'EmpresaAlfaFilter' in resp_vista.data

    # 4. Filtrar por EMPRESA
    resp_f_empresa = client.get('/productos?empresa=EmpresaAlfaFilter')
    assert resp_f_empresa.status_code == 200
    assert b'COD-FILTER-777' in resp_f_empresa.data

    # 5. Filtrar por CÓDIGO
    resp_f_codigo = client.get('/productos?codigo=FILTER-777')
    assert resp_f_codigo.status_code == 200
    assert b'Laptop Gaming Extreme 777' in resp_f_codigo.data

    # 6. Filtrar por DESCRIPCIÓN
    resp_f_desc = client.get('/productos?descripcion=Gaming Extreme')
    assert resp_f_desc.status_code == 200
    assert b'COD-FILTER-777' in resp_f_desc.data

    # 7. Filtrar por MARCA
    resp_f_marca = client.get('/productos?marca=MarcaOmegaFilter')
    assert resp_f_marca.status_code == 200
    assert b'COD-FILTER-777' in resp_f_marca.data

    # 8. Filtrar por CATEGORÍA
    resp_f_cat = client.get(f'/productos?categoria={cat_id}')
    assert resp_f_cat.status_code == 200
    assert b'Laptop Gaming Extreme 777' in resp_f_cat.data

    # Clean up
    client.delete(f'/api/categorias/{cat_id}')

def test_eliminar_productos_masivo(client, admin_user):
    client.post('/login', data={'correo': admin_user['email'], 'contrasena': admin_user['password']})

    # Crear 3 productos de prueba
    ids_creados = []
    for i in range(1, 4):
        client.post('/productos', data={
            'empresa': 'EmpresaBulk',
            'codigo': f'BULK-00{i}',
            'descripcion': f'Producto Bulk {i}',
            'marca': 'MarcaBulk',
            'tm': 'TM',
            'um': 'PZ',
            'cantidad': '10',
            'precio_unitario': '100'
        })
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM productos WHERE codigo = ?", (f'BULK-00{i}',))
        row = c.fetchone()
        conn.close()
        if row:
            ids_creados.append(row[0])

    assert len(ids_creados) == 3

    # Ejecutar eliminación masiva vía POST /productos/eliminar-masivo
    resp_bulk = client.post('/productos/eliminar-masivo', json={'ids': ids_creados})
    assert resp_bulk.status_code == 200
    res_json = resp_bulk.get_json()
    assert res_json['success'] is True
    assert '3 producto(s) eliminado(s)' in res_json['message']

    # Verificar en BD que ya no existen
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?, ?)", tuple(ids_creados))
    count = c.fetchone()[0]
    conn.close()
    assert count == 0
