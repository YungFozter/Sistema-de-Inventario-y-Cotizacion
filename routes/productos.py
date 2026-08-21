from flask import Flask, flash, render_template, request, redirect, session, url_for, make_response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pdfkit
from num2words import num2words
from datetime import datetime
import os
import time
import base64
import json
import sqlite3
import random
import string
from db_wrapper import get_db_connection
from sqlite3 import connect  # Esta es la importación que faltaba
from markupsafe import Markup
from threading import Lock
from contextlib import contextmanager
from models import (
    crear_tablas, registrar_log, migrar_clientes_existentes, migrar_productos_categorias,
    migrar_columnas_nuevas_clientes,
    guardar_importacion_pdf, obtener_importaciones_pdf, obtener_importacion_por_id, registrar_productos_seleccionados,
    eliminar_importacion_pdf
)
from utils.pdf_extractor import PDFProductExtractor
from utils.exchange_rate import obtener_tipo_cambio_paralelo
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
import logging
from utils.decorators import login_required, superadmin_required, admin_required, standard_required
from utils.helpers import format_date, aplicar_fondos_por_pagina, generar_pdf_margenes_dinamicos

def _obtener_columnas_productos(cursor):
    """Devuelve los nombres de las columnas de la tabla productos de forma compatible con SQLite y PostgreSQL"""
    try:
        is_pg = bool(os.environ.get('DATABASE_URL') and 'postgres' in os.environ.get('DATABASE_URL'))
        if is_pg:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'productos'")
            cols = [col[0] for col in cursor.fetchall()]
            if cols:
                return cols
        cursor.execute("PRAGMA table_info(productos)")
        return [col[1] for col in cursor.fetchall()]
    except Exception:
        return ['id', 'empresa', 'codigo', 'descripcion', 'marca', 'tm', 'um', 'cantidad', 'precio_unitario', 'precio_total', 'categoria_id', 'categoria', 'proveedor', 'proveedor_id', 'campos_personalizados', 'es_importado']

def _obtener_empresa_usuario(cursor, user_id, user_rol):
    """Devuelve la empresa/organización del usuario actual para aislamiento multi-tenant"""
    if user_rol == 'superadmin':
        return None
    cursor.execute("SELECT nombre, empresa_nombre, creador_id, rol FROM clientes WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    if not u:
        return 'General'
    nombre = u['nombre'] if hasattr(u, 'keys') else u[0]
    empresa_nom = u['empresa_nombre'] if hasattr(u, 'keys') else u[1]
    creador_id = u['creador_id'] if hasattr(u, 'keys') else u[2]
    rol = u['rol'] if hasattr(u, 'keys') else u[3]
    
    if empresa_nom and empresa_nom.strip():
        return empresa_nom.strip()
    if rol == 'standard' and creador_id:
        cursor.execute("SELECT nombre, empresa_nombre FROM clientes WHERE id = ?", (creador_id,))
        p = cursor.fetchone()
        if p:
            p_emp = p['empresa_nombre'] if hasattr(p, 'keys') else p[1]
            p_nom = p['nombre'] if hasattr(p, 'keys') else p[0]
            return (p_emp or p_nom or 'General').strip()
    return (nombre or 'General').strip()

def register_routes(app):
    @app.route('/productos', methods=['GET', 'POST'], strict_slashes=False)
    @login_required
    @admin_required
    def productos():
        mensaje_error = None
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        # Manejo del formulario POST (registro de nuevos productos)
        if request.method == 'POST':
            try:
                with get_db_connection() as conexion:
                    cursor = conexion.cursor()
                
                    user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
                    empresa = request.form.get('empresa', '').strip()
                    if not empresa or user_rol != 'superadmin':
                        empresa = user_empresa or 'General'
                    codigo = request.form.get('codigo', '').strip()
                    descripcion = request.form.get('descripcion', '').strip()
                    marca = request.form.get('marca', '').strip()
                    tm = request.form.get('tm', 'Bs').strip()
                    um = request.form.get('um', 'Pza').strip()

                    try:
                        cant_str = str(request.form.get('cantidad', '1')).replace(',', '.').strip()
                        cantidad = int(float(cant_str)) if cant_str else 1
                    except (ValueError, TypeError):
                        cantidad = 1

                    try:
                        precio_str = str(request.form.get('precio_unitario', '0')).replace(',', '.').strip()
                        precio_unitario = float(precio_str) if precio_str else 0.0
                    except (ValueError, TypeError):
                        precio_unitario = 0.0

                    precio_total = cantidad * precio_unitario
                    categoria_id = request.form.get('categoria_id')
                    if not categoria_id:
                        categoria_id = None

                    proveedor = request.form.get('proveedor', '').strip()

                    # Validar si ya existe combinación empresa + codigo
                    cursor.execute("SELECT COUNT(*) FROM productos WHERE empresa=? AND codigo=?", (empresa, codigo))
                    existe = cursor.fetchone()[0]

                    if existe > 0:
                        mensaje_error = f"⚠️ El código '{codigo}' ya existe para la empresa '{empresa}'."
                    else:
                        columnas_nombres = _obtener_columnas_productos(cursor)
                    
                        categoria_nombre = None
                        if categoria_id:
                            cursor.execute("SELECT nombre FROM categorias WHERE id = ?", (categoria_id,))
                            resultado = cursor.fetchone()
                            if resultado:
                                categoria_nombre = resultado[0]

                        cols = ['empresa', 'codigo', 'descripcion', 'marca', 'tm', 'um', 'cantidad', 'precio_unitario', 'precio_total', 'categoria_id', 'categoria']
                        vals = [empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total, categoria_id, categoria_nombre]

                        if 'proveedor' in columnas_nombres:
                            prov_id = None
                            if proveedor:
                                try:
                                    user_id = session.get('user_id')
                                    cursor.execute("SELECT id, nombre FROM proveedores WHERE (creador_id = ? OR empresa = ?) AND LOWER(nombre) = LOWER(?)", (user_id, empresa, proveedor))
                                    p_row = cursor.fetchone()
                                    if not p_row:
                                        cursor.execute('''
                                            INSERT INTO proveedores (empresa, nombre, contacto_nombre, rubro, creador_id)
                                            VALUES (?, ?, 'N/A', 'Suministros', ?)
                                        ''', (empresa, proveedor, user_id))
                                        prov_id = cursor.lastrowid
                                    else:
                                        prov_id = p_row[0]
                                        proveedor = p_row[1]
                                except Exception as e_p:
                                    print(f"[WARN] Error resolviendo proveedor en creación: {e_p}")

                            cols.append('proveedor')
                            vals.append(proveedor)
                            if 'proveedor_id' in columnas_nombres:
                                cols.append('proveedor_id')
                                vals.append(prov_id)

                        if 'es_importado' in columnas_nombres:
                            cols.append('es_importado')
                            vals.append(0)

                        placeholders = ', '.join(['?'] * len(vals))
                        cols_str = ', '.join(cols)
                        cursor.execute(f"INSERT INTO productos ({cols_str}) VALUES ({placeholders})", vals)
                    
                        conexion.commit()

            except Exception as e:
                mensaje_error = f"Error al registrar el producto: {str(e)}"

        # Lógica de búsqueda
        empresa = request.args.get('empresa', '')
        proveedor = request.args.get('proveedor', '')
        codigo = request.args.get('codigo', '')
        descripcion = request.args.get('descripcion', '')
        marca = request.args.get('marca', '')
        categoria = request.args.get('categoria', '')
        tab_activa = request.args.get('tab', 'registrados')
    
        # Paginación independiente para ambas tablas
        page_reg = request.args.get('page_reg', request.args.get('page', 1, type=int), type=int)
        page_imp = request.args.get('page_imp', 1, type=int)
        try:
            per_page = int(request.args.get('per_page', 5))
        except (ValueError, TypeError):
            per_page = 5
        if per_page not in [5, 15, 30]:
            per_page = 5

        columnas_nombres = []
        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                columnas_nombres = _obtener_columnas_productos(cursor)

            if 'categoria_id' in columnas_nombres:
                base_query = "SELECT p.*, c.nombre as categoria_nombre FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id WHERE 1=1"
                count_query = "SELECT COUNT(*) FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id WHERE 1=1"
                use_alias = True
            else:
                base_query = "SELECT *, categoria as categoria_nombre FROM productos WHERE 1=1"
                count_query = "SELECT COUNT(*) FROM productos WHERE 1=1"
                use_alias = False
        except Exception as e:
            base_query = "SELECT * FROM productos WHERE 1=1"
            count_query = "SELECT COUNT(*) FROM productos WHERE 1=1"
            use_alias = False

        filter_sql = ""
        params = []

        if user_rol != 'superadmin':
            user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
            if user_empresa:
                filter_sql += " AND (p.empresa = ? OR p.empresa = 'General')" if use_alias else " AND (empresa = ? OR empresa = 'General')"
                params.append(user_empresa)

        if empresa:
            filter_sql += " AND p.empresa LIKE ?" if use_alias else " AND empresa LIKE ?"
            params.append(f"%{empresa}%")
        if proveedor and 'proveedor' in columnas_nombres:
            filter_sql += " AND p.proveedor LIKE ?" if use_alias else " AND proveedor LIKE ?"
            params.append(f"%{proveedor}%")
        if codigo:
            filter_sql += " AND p.codigo LIKE ?" if use_alias else " AND codigo LIKE ?"
            params.append(f"%{codigo}%")
        if descripcion:
            filter_sql += " AND (p.descripcion LIKE ? OR p.empresa LIKE ?)" if use_alias else " AND (descripcion LIKE ? OR empresa LIKE ?)"
            params.extend([f"%{descripcion}%", f"%{descripcion}%"])
        if marca:
            filter_sql += " AND p.marca LIKE ?" if use_alias else " AND marca LIKE ?"
            params.append(f"%{marca}%")
        if categoria:
            cat_nombre = None
            if str(categoria).isdigit():
                try:
                    with get_db_connection() as conexion_cat:
                        cursor_cat = conexion_cat.cursor()
                        cursor_cat.execute("SELECT nombre FROM categorias WHERE id = ?", (int(categoria),))
                        res_cat = cursor_cat.fetchone()
                        if res_cat:
                            cat_nombre = res_cat[0]
                except Exception:
                    pass

            if str(categoria).isdigit():
                cat_id_num = int(categoria)
                cat_target_name = cat_nombre or str(categoria)
                if use_alias:
                    filter_sql += " AND (p.categoria_id = ? OR c.id = ? OR LOWER(p.categoria) = LOWER(?) OR LOWER(p.categoria) = LOWER(?))"
                    params.extend([cat_id_num, cat_id_num, str(categoria), cat_target_name])
                else:
                    filter_sql += " AND (categoria_id = ? OR LOWER(categoria) = LOWER(?) OR LOWER(categoria) = LOWER(?))"
                    params.extend([cat_id_num, str(categoria), cat_target_name])
            else:
                if use_alias:
                    filter_sql += " AND (LOWER(c.nombre) LIKE LOWER(?) OR LOWER(p.categoria) LIKE LOWER(?))"
                    params.extend([f"%{categoria}%", f"%{categoria}%"])
                else:
                    filter_sql += " AND LOWER(categoria) LIKE LOWER(?)"
                    params.append(f"%{categoria}%")

        # 1. Consultar Productos Registrados (Manuales: es_importado = 0 o NULL)
        cond_reg = " AND (p.es_importado IS NULL OR p.es_importado = 0)" if use_alias else " AND (es_importado IS NULL OR es_importado = 0)"
        offset_reg = (page_reg - 1) * per_page

        # 2. Consultar Productos Importados (PDF/Texto: es_importado = 1)
        cond_imp = " AND p.es_importado = 1" if use_alias else " AND es_importado = 1"
        offset_imp = (page_imp - 1) * per_page

        productos_registrados = []
        total_registrados = 0
        total_pages_reg = 1

        productos_importados = []
        total_importados = 0
        total_pages_imp = 1

        try:
            with get_db_connection() as conexion:
                conexion.row_factory = sqlite3.Row
                cursor = conexion.cursor()

                # Registrados
                cursor.execute(count_query + filter_sql + cond_reg, params)
                total_registrados = cursor.fetchone()[0]
                total_pages_reg = max(1, (total_registrados + per_page - 1) // per_page)
                cursor.execute(base_query + filter_sql + cond_reg + " ORDER BY id DESC LIMIT ? OFFSET ?", params + [per_page, offset_reg])
                productos_registrados = [dict(row) for row in cursor.fetchall()]

                # Importados
                cursor.execute(count_query + filter_sql + cond_imp, params)
                total_importados = cursor.fetchone()[0]
                total_pages_imp = max(1, (total_importados + per_page - 1) // per_page)
                cursor.execute(base_query + filter_sql + cond_imp + " ORDER BY id DESC LIMIT ? OFFSET ?", params + [per_page, offset_imp])
                productos_importados = [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            mensaje_error = f"Error al buscar productos: {str(e)}"

        filtros = {
            'empresa': empresa,
            'proveedor': proveedor,
            'codigo': codigo,
            'descripcion': descripcion,
            'marca': marca,
            'categoria': categoria
        }

        pagination_reg = {
            'page': page_reg,
            'per_page': per_page,
            'total_pages': total_pages_reg,
            'total_items': total_registrados
        }

        pagination_imp = {
            'page': page_imp,
            'per_page': per_page,
            'total_pages': total_pages_imp,
            'total_items': total_importados
        }

        if request.args.get('ajax') == '1':
            html_registrados = render_template(
                'productos/_tabla_registrados.html',
                productos_registrados=productos_registrados,
                pagination_reg=pagination_reg,
                pagination_imp=pagination_imp,
                filtros=filtros
            )
            return jsonify({
                'success': True,
                'html_registrados': html_registrados,
                'pagination_reg': pagination_reg
            })

        # Obtener clientes para el modal de PDF Directo y empresas para Superadmin
        clientes = []
        lista_empresas = []
        lista_proveedores = []
        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                if session.get('user_rol') == 'superadmin':
                    cursor.execute("SELECT id, nombre FROM clientes WHERE rol = 'cliente' ORDER BY nombre")
                    clientes = cursor.fetchall()
                    cursor.execute("SELECT DISTINCT empresa FROM productos WHERE empresa IS NOT NULL AND empresa != '' ORDER BY empresa")
                    lista_empresas = [row[0] for row in cursor.fetchall()]
                else:
                    admin_owner_id = session.get('creador_id') or session.get('user_id')
                    cursor.execute("SELECT id, nombre FROM clientes WHERE (creador_id = ? OR creador_id = ?) AND rol = 'cliente' ORDER BY nombre", 
                                   (admin_owner_id, session['user_id']))
                    clientes = cursor.fetchall()
                    user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
                    lista_empresas = [user_empresa] if user_empresa else ['General']

                cursor.execute("SELECT nombre FROM proveedores ORDER BY nombre ASC")
                lista_proveedores = [row[0] for row in cursor.fetchall()]
        except Exception:
            clientes = []
            lista_empresas = []
            lista_proveedores = []

        return render_template(
            'productos/productos.html',
            productos=productos_registrados,
            productos_registrados=productos_registrados,
            productos_importados=productos_importados,
            mensaje_error=mensaje_error,
            filtros=filtros,
            pagination=pagination_reg,
            pagination_reg=pagination_reg,
            pagination_imp=pagination_imp,
            tab_activa=tab_activa,
            clientes=clientes,
            lista_empresas=lista_empresas,
            lista_proveedores=lista_proveedores,
            tipo_cambio_live=obtener_tipo_cambio_paralelo()
        )

    @app.route('/productos/editar/<int:id>', methods=['GET', 'POST'], strict_slashes=False)
    @login_required
    @admin_required
    def editar_producto(id):
        tab = request.form.get('tab', request.args.get('tab', 'registrados'))
        page_reg = request.form.get('page_reg', request.args.get('page_reg', 1))
        page_imp = request.form.get('page_imp', request.args.get('page_imp', 1))
    
        empresa_filtro = request.form.get('empresa_filtro', request.args.get('empresa', ''))
        proveedor_filtro = request.form.get('proveedor_filtro', request.args.get('proveedor', ''))
        codigo_filtro = request.form.get('codigo_filtro', request.args.get('codigo', ''))
        descripcion_filtro = request.form.get('descripcion_filtro', request.args.get('descripcion', ''))
        marca_filtro = request.form.get('marca_filtro', request.args.get('marca', ''))
        categoria_filtro = request.form.get('categoria_filtro', request.args.get('categoria', ''))

        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        # Validar permisos sobre el producto antes de editar
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
            cursor.execute('SELECT id, empresa FROM productos WHERE id=?', (id,))
            target_prod = cursor.fetchone()
            if not target_prod:
                flash('Producto no encontrado', 'danger')
                return redirect(url_for('productos'))
            
            p_emp = target_prod[1] if isinstance(target_prod, tuple) else target_prod['empresa']
            if user_rol != 'superadmin' and p_emp != user_empresa and p_emp != 'General':
                flash('No tienes permisos para modificar productos de otra empresa.', 'danger')
                return redirect(url_for('productos'))

        if request.method == 'POST':
            try:
                empresa = request.form.get('empresa', '').strip()
                if not empresa or user_rol != 'superadmin':
                    empresa = user_empresa or 'General'
                proveedor = request.form.get('proveedor', '').strip()
                codigo = request.form.get('codigo', '').strip()
                descripcion = request.form.get('descripcion', '').strip()
                marca = request.form.get('marca', '').strip()
                tm = request.form.get('tm', 'Bs').strip()
                um = request.form.get('um', 'Pza').strip()

                try:
                    cant_str = str(request.form.get('cantidad', '1')).replace(',', '.').strip()
                    cantidad = int(float(cant_str)) if cant_str else 1
                except (ValueError, TypeError):
                    cantidad = 1

                try:
                    precio_str = str(request.form.get('precio_unitario', '0')).replace(',', '.').strip()
                    precio_unitario = float(precio_str) if precio_str else 0.0
                except (ValueError, TypeError):
                    precio_unitario = 0.0

                precio_total = cantidad * precio_unitario
                categoria_id = request.form.get('categoria_id')
                if not categoria_id:
                    categoria_id = None
            
                with get_db_connection() as conexion:
                    cursor = conexion.cursor()
                
                    categoria_nombre = None
                    if categoria_id:
                        cursor.execute("SELECT nombre FROM categorias WHERE id = ?", (categoria_id,))
                        resultado = cursor.fetchone()
                        if resultado:
                            categoria_nombre = resultado[0]
                
                    columnas_nombres = _obtener_columnas_productos(cursor)
                
                    update_cols = ['empresa=?', 'codigo=?', 'descripcion=?', 'marca=?', 'tm=?', 'um=?', 'cantidad=?', 'precio_unitario=?', 'precio_total=?']
                    update_vals = [empresa, codigo, descripcion, marca, tm, um, cantidad, precio_unitario, precio_total]

                    if 'categoria_id' in columnas_nombres:
                        update_cols.extend(['categoria_id=?', 'categoria=?'])
                        update_vals.extend([categoria_id, categoria_nombre])
                    else:
                        update_cols.append('categoria=?')
                        update_vals.append(categoria_nombre)

                    if 'proveedor' in columnas_nombres:
                        prov_id = None
                        if proveedor:
                            try:
                                cursor.execute("SELECT id, nombre FROM proveedores WHERE (creador_id = ? OR empresa = ?) AND LOWER(nombre) = LOWER(?)", (user_id, empresa, proveedor))
                                p_row = cursor.fetchone()
                                if not p_row:
                                    cursor.execute('''
                                        INSERT INTO proveedores (empresa, nombre, contacto_nombre, rubro, creador_id)
                                        VALUES (?, ?, 'N/A', 'Suministros', ?)
                                    ''', (empresa, proveedor, user_id))
                                    prov_id = cursor.lastrowid
                                else:
                                    prov_id = p_row[0]
                                    proveedor = p_row[1]
                            except Exception as e_p:
                                print(f"[WARN] Error resolviendo proveedor en edición: {e_p}")

                        update_cols.append('proveedor=?')
                        update_vals.append(proveedor)
                        if 'proveedor_id' in columnas_nombres:
                            update_cols.append('proveedor_id=?')
                            update_vals.append(prov_id)

                    # Recolectar campos personalizados desde el formulario
                    custom_fields_dict = {}
                    for key, val in request.form.items():
                        if key.startswith('campo_personalizado_'):
                            c_name = key.replace('campo_personalizado_', '')
                            custom_fields_dict[c_name] = val.strip()

                    if 'campos_personalizados' in columnas_nombres and custom_fields_dict:
                        update_cols.append('campos_personalizados=?')
                        update_vals.append(json.dumps(custom_fields_dict, ensure_ascii=False))

                    update_vals.append(id)
                    update_str = ', '.join(update_cols)

                    cursor.execute(f'UPDATE productos SET {update_str} WHERE id=?', update_vals)
                    conexion.commit()

                    registrar_log(
                        usuario_id=user_id,
                        accion="editar_producto",
                        detalle={"producto_id": id, "codigo": codigo, "empresa": empresa}
                    )
            
                flash('Producto actualizado correctamente', 'success')
                return redirect(url_for('productos', tab=tab, page_reg=page_reg, page_imp=page_imp, empresa=empresa_filtro, codigo=codigo_filtro, descripcion=descripcion_filtro, marca=marca_filtro, categoria=categoria_filtro))
        
            except Exception as e:
                flash(f'Error al actualizar el producto: {str(e)}', 'danger')
                return redirect(url_for('editar_producto', id=id, tab=tab, page_reg=page_reg, page_imp=page_imp, empresa=empresa_filtro, codigo=codigo_filtro, descripcion=descripcion_filtro, marca=marca_filtro, categoria=categoria_filtro))

        # GET - Mostrar formulario de edición
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
        
            cursor.execute('SELECT * FROM productos WHERE id=?', (id,))
            row = cursor.fetchone()
            producto = dict(row) if row else {}
        
            cursor.execute('''
                SELECT DISTINCT c.id, c.nombre 
                FROM categorias c 
                INNER JOIN productos p ON c.id = p.categoria_id 
                ORDER BY c.nombre
            ''')
            categorias_en_uso = [dict(r) if hasattr(r, 'keys') else r for r in cursor.fetchall()]
        
            cursor.execute('SELECT id, nombre FROM categorias WHERE activo = 1 AND (creador_id = ? OR creador_id IS NULL) ORDER BY nombre', (user_id,))
            todas_categorias = [dict(r) if hasattr(r, 'keys') else r for r in cursor.fetchall()]
        
            categorias = categorias_en_uso if categorias_en_uso else todas_categorias

            cursor.execute("SELECT nombre FROM proveedores ORDER BY nombre ASC")
            lista_proveedores = [r[0] for r in cursor.fetchall()]
    
        filtros = {
            'empresa': empresa_filtro,
            'proveedor': proveedor_filtro,
            'codigo': codigo_filtro,
            'descripcion': descripcion_filtro,
            'marca': marca_filtro,
            'categoria': categoria_filtro
        }

        return render_template(
            'productos/editar_producto.html',
            producto=producto,
            producto_id=id,
            categorias=categorias,
            todas_categorias=todas_categorias,
            lista_proveedores=lista_proveedores,
            tab=tab,
            page_reg=page_reg,
            page_imp=page_imp,
            filtros=filtros
        )

    @app.route('/productos/eliminar-masivo', methods=['POST'])
    @login_required
    @admin_required
    def eliminar_productos_masivo():
        try:
            data = request.get_json() or {}
            ids = data.get('ids', [])
            if not ids or not isinstance(ids, list):
                return jsonify({'success': False, 'message': 'No se seleccionaron productos para eliminar.'}), 400

            user_id = session.get('user_id')
            user_rol = session.get('user_rol')

            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
                placeholders = ','.join(['?'] * len(ids))
                if user_rol != 'superadmin':
                    cursor.execute(f'DELETE FROM productos WHERE id IN ({placeholders}) AND (empresa = ? OR empresa = "General")', ids + [user_empresa])
                else:
                    cursor.execute(f'DELETE FROM productos WHERE id IN ({placeholders})', ids)
                deleted_count = cursor.rowcount
                conexion.commit()

                registrar_log(
                    usuario_id=user_id,
                    accion="eliminar_productos_masivo",
                    detalle={"total_eliminados": deleted_count, "ids": ids}
                )

            return jsonify({
                'success': True,
                'message': f'{deleted_count} producto(s) eliminado(s) correctamente.'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al eliminar los productos: {str(e)}'}), 500

    @app.route('/productos/eliminar/<int:id>')
    @login_required
    @admin_required
    def eliminar_producto(id):
        try:
            user_id = session.get('user_id')
            user_rol = session.get('user_rol')
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)
                cursor.execute('SELECT id, codigo, empresa FROM productos WHERE id=?', (id,))
                prod = cursor.fetchone()
                if not prod:
                    flash('Producto no encontrado', 'danger')
                    return redirect('/productos')

                p_emp = prod[2] if isinstance(prod, tuple) else prod['empresa']
                if user_rol != 'superadmin' and p_emp != user_empresa and p_emp != 'General':
                    flash('No tienes permisos para eliminar productos de otra empresa.', 'danger')
                    return redirect('/productos')

                cursor.execute('DELETE FROM productos WHERE id=?', (id,))
                conexion.commit()

                registrar_log(
                    usuario_id=user_id,
                    accion="eliminar_producto",
                    detalle={"producto_id": id, "codigo": prod[1] if isinstance(prod, tuple) else prod['codigo']}
                )
            flash('Producto eliminado correctamente', 'success')
        except Exception as e:
            flash(f'Error al eliminar el producto: {str(e)}', 'danger')
        return redirect('/productos')

    @app.route('/api/categorias', methods=['GET'])
    @login_required
    def api_categorias():
        """API para obtener todas las categorías"""
        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()
        
            user_id = session.get('user_id')
            cursor.execute("SELECT id, nombre, descripcion FROM categorias WHERE (activo IS TRUE OR activo = 1) AND (creador_id = ? OR creador_id IS NULL) ORDER BY nombre", (user_id,))
            categorias = cursor.fetchall()
        
            # Convertir a lista de diccionarios
            categorias_list = [
                {'id': cat[0], 'nombre': cat[1], 'descripcion': cat[2]}
                for cat in categorias
            ]
        
            conexion.close()
            return jsonify(categorias_list)
        
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/categorias', methods=['POST'])
    @login_required
    def api_crear_categoria():
        """API para crear una nueva categoría"""
        try:
            data = request.get_json() or {}
            nombre = data.get('nombre', '').strip()
            descripcion = data.get('descripcion', '').strip()
        
            if not nombre:
                return jsonify({'success': False, 'message': 'El nombre de la categoría es requerido'})
        
            conexion = get_db_connection()
            cursor = conexion.cursor()
        
            user_id = session.get('user_id')
            
            # Verificar si la categoría ya existe (activa o inactiva) para este admin o global
            cursor.execute("SELECT id, activo FROM categorias WHERE LOWER(nombre) = LOWER(?) AND (creador_id = ? OR creador_id IS NULL)", (nombre, user_id))
            existente = cursor.fetchone()

            if existente:
                cat_id, activo = existente[0], existente[1]
                if activo:
                    conexion.close()
                    return jsonify({'success': False, 'message': f'Ya existe una categoría con el nombre "{nombre}"'})
                else:
                    # Reactivar categoría borrada lógicamente
                    cursor.execute(
                        "UPDATE categorias SET activo = TRUE, descripcion = ? WHERE id = ?",
                        (descripcion, cat_id)
                    )
                    conexion.commit()
                    conexion.close()
                    return jsonify({'success': True, 'categoria_id': cat_id, 'message': f'Categoría "{nombre}" reactivada exitosamente'})
        
            # Crear la nueva categoría
            cursor.execute(
                "INSERT INTO categorias (nombre, descripcion, activo, creador_id) VALUES (?, ?, TRUE, ?)",
                (nombre, descripcion, user_id)
            )
            categoria_id = cursor.lastrowid
            conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="crear_categoria",
                detalle={"categoria_id": categoria_id, "nombre": nombre, "descripcion": descripcion}
            )

            conexion.close()
        
            return jsonify({'success': True, 'categoria_id': categoria_id, 'message': f'Categoría "{nombre}" creada exitosamente'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al crear la categoría: {str(e)}'})

    @app.route('/api/categorias/<int:categoria_id>', methods=['PUT', 'POST'])
    @login_required
    @admin_required
    def api_editar_categoria(categoria_id):
        """API para editar una categoría existente"""
        try:
            data = request.get_json() or {}
            nombre = data.get('nombre', '').strip()
            descripcion = data.get('descripcion', '').strip()

            if not nombre:
                return jsonify({'success': False, 'message': 'El nombre de la categoría es requerido'})

            conexion = get_db_connection()
            cursor = conexion.cursor()

            user_id = session.get('user_id')
            
            # Verificar si la categoría existe y pertenece a este admin
            cursor.execute("SELECT id, creador_id FROM categorias WHERE id = ? AND (activo IS TRUE OR activo = 1)", (categoria_id,))
            cat_actual = cursor.fetchone()
            if not cat_actual:
                conexion.close()
                return jsonify({'success': False, 'message': 'Categoría no encontrada'})
            
            if cat_actual[1] is not None and cat_actual[1] != user_id:
                conexion.close()
                return jsonify({'success': False, 'message': 'No tienes permiso para editar esta categoría'})

            # Verificar si otra categoría activa ya tiene ese mismo nombre para este admin
            cursor.execute("SELECT id FROM categorias WHERE nombre = ? AND id != ? AND (activo IS TRUE OR activo = 1) AND (creador_id = ? OR creador_id IS NULL)", (nombre, categoria_id, user_id))
            if cursor.fetchone():
                conexion.close()
                return jsonify({'success': False, 'message': 'Ya existe otra categoría con ese nombre'})

            # Actualizar la categoría
            cursor.execute(
                "UPDATE categorias SET nombre = ?, descripcion = ? WHERE id = ?",
                (nombre, descripcion, categoria_id)
            )

            # También actualizar el campo desnormalizado en productos si aplica
            try:
                cursor.execute(
                    "UPDATE productos SET categoria = ? WHERE categoria_id = ?",
                    (nombre, categoria_id)
                )
            except Exception:
                pass

            conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="editar_categoria",
                detalle={"categoria_id": categoria_id, "nombre": nombre, "descripcion": descripcion}
            )

            conexion.close()

            return jsonify({'success': True, 'message': 'Categoría actualizada exitosamente'})

        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al actualizar la categoría: {str(e)}'})

    @app.route('/api/categorias/<int:categoria_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def api_eliminar_categoria(categoria_id):
        """API para eliminar una categoría"""
        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()
        
            user_id = session.get('user_id')
            
            # Verificar si la categoría existe y si el usuario tiene permisos
            cursor.execute("SELECT nombre, creador_id FROM categorias WHERE id = ? AND (activo IS TRUE OR activo = 1)", (categoria_id,))
            categoria = cursor.fetchone()
        
            if not categoria:
                conexion.close()
                return jsonify({'success': False, 'message': 'Categoría no encontrada'})
                
            if categoria[1] is not None and categoria[1] != user_id:
                conexion.close()
                return jsonify({'success': False, 'message': 'No tienes permiso para eliminar esta categoría'})
        
            # Verificar si hay productos usando esta categoría
            cursor.execute("SELECT COUNT(*) FROM productos WHERE categoria_id = ?", (categoria_id,))
            productos_usando = cursor.fetchone()[0]
        
            if productos_usando > 0:
                conexion.close()
                return jsonify({
                    'success': False, 
                    'message': f'No se puede eliminar la categoría "{categoria[0]}" porque está siendo utilizada por {productos_usando} producto(s)'
                })
        
            # Eliminar la categoría (marcado lógico)
            cursor.execute("UPDATE categorias SET activo = FALSE WHERE id = ?", (categoria_id,))
            conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="eliminar_categoria",
                detalle={"categoria_id": categoria_id, "nombre": categoria[0]}
            )

            conexion.close()
        
            return jsonify({'success': True, 'message': f'Categoría "{categoria[0]}" eliminada exitosamente'})
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al eliminar la categoría: {str(e)}'})

    @app.route('/productos/importar-pdf', methods=['POST'])
    @login_required
    @admin_required
    def importar_pdf_productos():
        """Recibe un archivo PDF, extrae las celdas de la tabla omitiendo #, Procedencia, Cantidad y Total"""
        if 'archivo_pdf' not in request.files:
            return jsonify({'success': False, 'message': 'No se proporcionó ningún archivo PDF'}), 400

        archivo = request.files['archivo_pdf']
        consolidar = request.form.get('consolidar_duplicados', 'true').lower() == 'true'

        if archivo.filename == '' or not archivo.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'message': 'El archivo debe ser un PDF válido (.pdf)'}), 400

        try:
            pdf_bytes = archivo.read()
            raw_items = PDFProductExtractor.extract_products(pdf_bytes, consolidar_duplicados=False)
            consolidated_items = PDFProductExtractor.extract_products(pdf_bytes, consolidar_duplicados=True)
            duplicados = PDFProductExtractor.detectar_duplicados(raw_items)

            items_to_return = consolidated_items if consolidar else raw_items

            if not items_to_return:
                return jsonify({
                    'success': False,
                    'message': 'No se encontraron filas de productos válidos en el PDF. Verifique que el documento contenga una tabla con productos.'
                }), 422

            return jsonify({
                'success': True,
                'nombre_sugerido': os.path.splitext(archivo.filename)[0],
                'total_extraidos': len(raw_items),
                'total_unicos': len(consolidated_items),
                'duplicados': duplicados,
                'has_duplicates': len(duplicados) > 0,
                'consolidar_activo': consolidar,
                'products': items_to_return
            })

        except Exception as e:
            app.logger.error(f"Error procesando PDF: {e}")
            return jsonify({'success': False, 'message': f'Error procesando el PDF: {str(e)}'}), 500

    @app.route('/productos/pegar-texto', methods=['POST'])
    @login_required
    @admin_required
    def procesar_texto_pegado():
        """Recibe texto copiado/pegado directamente por el usuario de una tabla y extrae los productos"""
        try:
            data = request.get_json() or {}
            texto = data.get('texto', '').strip()
            consolidar = data.get('consolidar_duplicados', True)

            if not texto:
                return jsonify({'success': False, 'message': 'No se proporcionó ningún texto para procesar'}), 400

            raw_items = PDFProductExtractor.parse_pasted_text(texto, consolidar_duplicados=False)
            consolidated_items = PDFProductExtractor.parse_pasted_text(texto, consolidar_duplicados=True)
            duplicados = PDFProductExtractor.detectar_duplicados(raw_items)

            items_to_return = consolidated_items if consolidar else raw_items

            if not items_to_return:
                return jsonify({
                    'success': False,
                    'message': 'No se identificaron filas de productos en el texto pegado. Asegúrese de incluir las filas de la tabla.'
                }), 422

            return jsonify({
                'success': True,
                'total_extraidos': len(raw_items),
                'total_unicos': len(consolidated_items),
                'duplicados': duplicados,
                'has_duplicates': len(duplicados) > 0,
                'consolidar_activo': consolidar,
                'products': items_to_return
            })

        except Exception as e:
            return jsonify({'success': False, 'message': f'Error procesando el texto: {str(e)}'}), 500

    @app.route('/productos/guardar-importacion', methods=['POST'])

    @login_required
    @admin_required
    def guardar_importacion_route():
        """Guarda un lote de importación con su nombre y sus items editados"""
        try:
            data = request.get_json() or {}
            nombre_importacion = data.get('nombre_importacion', '').strip()
            items = data.get('items', [])

            if not items:
                return jsonify({'success': False, 'message': 'No hay productos para guardar en la importación'}), 400

            importacion_id, nombre_final = guardar_importacion_pdf(
                nombre_importacion=nombre_importacion,
                items=items,
                usuario_id=session.get('user_id')
            )

            return jsonify({
                'success': True,
                'importacion_id': importacion_id,
                'nombre_importacion': nombre_final,
                'message': f'Importación "{nombre_final}" guardada exitosamente en el historial.'
            })


        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al guardar importación: {str(e)}'}), 500

    @app.route('/productos/importaciones', methods=['GET'])
    @login_required
    def listar_importaciones():
        """Retorna la lista de importaciones guardadas filtradas por usuario"""
        try:
            user_id = None if session.get('user_rol') == 'superadmin' else session.get('user_id')
            importaciones = obtener_importaciones_pdf(usuario_id=user_id)
            return jsonify({'success': True, 'importaciones': importaciones})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/productos/importacion/<int:importacion_id>', methods=['GET'])
    @login_required
    def detalle_importacion(importacion_id):
        """Retorna los datos de una importación guardada y sus items validando propiedad"""
        try:
            user_id = None if session.get('user_rol') == 'superadmin' else session.get('user_id')
            imp, items = obtener_importacion_por_id(importacion_id, usuario_id=user_id)
            if not imp:
                return jsonify({'success': False, 'message': 'Importación no encontrada o sin permisos de acceso'}), 404
            return jsonify({'success': True, 'importacion': imp, 'items': items})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/productos/importacion/<int:importacion_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def eliminar_importacion_route(importacion_id):
        """Elimina una importación guardada y sus items del historial validando propiedad"""
        try:
            user_id = None if session.get('user_rol') == 'superadmin' else session.get('user_id')
            eliminado = eliminar_importacion_pdf(importacion_id, usuario_id=user_id)
            if not eliminado:
                return jsonify({'success': False, 'message': 'Importación no encontrada o sin permisos para eliminar'}), 403
            return jsonify({'success': True, 'message': 'Importación eliminada correctamente del historial.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al eliminar la importación: {str(e)}'}), 500

    @app.route('/productos/registrar-seleccionados', methods=['POST'])
    @login_required
    @admin_required
    def registrar_seleccionados_route():
        """Registra los productos seleccionados de la importación en el catálogo oficial de productos"""
        try:
            data = request.get_json() or {}
            items = data.get('items', [])
            categoria_id = data.get('categoria_id')
            respetar_cantidades = data.get('respetar_cantidades', True)
            tipo_documento = data.get('tipo_documento', 'factura')

            user_id = session.get('user_id')
            user_rol = session.get('user_rol')
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                user_empresa = _obtener_empresa_usuario(cursor, user_id, user_rol)

            empresa = data.get('empresa', '').strip()
            if not empresa or user_rol != 'superadmin':
                empresa = user_empresa or 'General'

            if not items:
                return jsonify({'success': False, 'message': 'No se seleccionó ningún producto para registrar'}), 400

            count = registrar_productos_seleccionados(
                items=items,
                empresa=empresa,
                categoria_id=categoria_id,
                respetar_cantidades=respetar_cantidades,
                tipo_documento=tipo_documento
            )

            return jsonify({
                'success': True,
                'count': count,
                'message': f'Se registraron/actualizaron exitosamente {count} producto(s) en el catálogo de {empresa}.'
            })

        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al registrar productos: {str(e)}'}), 500

    @app.route('/cotizaciones/pdf_directo_importacion', methods=['POST'])
    @login_required
    def pdf_directo_importacion():
        try:
            if request.is_json:
                data = request.json
            else:
                data_str = request.form.get('data')
                if not data_str:
                    return "No data provided", 400
                import json
                data = json.loads(data_str)

            items = data.get('items', [])
            descuento_porcentaje = float(data.get('descuento_porcentaje', 0.0))
            nombre_cliente = data.get('nombre_cliente', 'Cliente (PDF Directo)')
            cliente_id = data.get('cliente_id')

            if not items:
                if request.is_json:
                    return jsonify({'success': False, 'message': 'No hay ítems para generar el PDF'})
                return "No hay ítems para generar el PDF", 400

            # Calcular totales
            subtotal_bruto = sum((float(item.get('cantidad', 1)) * float(item.get('precio_unitario', 0.0))) for item in items)
            monto_descuento = subtotal_bruto * (descuento_porcentaje / 100.0)
            total_final = max(0, subtotal_bruto - monto_descuento)

            def numero_a_palabras(numero):
                try:
                    if numero is None:
                        return "CERO BOLIVIANOS"
                    parte_entera = int(numero)
                    parte_decimal = int(round((numero - parte_entera) * 100))
                    palabras_entera = num2words(parte_entera, lang='es').upper()
                    palabras_decimal = num2words(parte_decimal, lang='es').upper()
                    resultado = f"{palabras_entera} BOLIVIANOS"
                    if parte_decimal > 0:
                        resultado += f" CON {palabras_decimal} CENTAVOS"
                    return resultado
                except Exception:
                    return "CERO BOLIVIANOS"

            total_letras = numero_a_palabras(total_final)
            fecha_cotizacion = datetime.now().strftime("%d/%m/%Y")

            # Cargar imagen de fondo
            fondo_path = os.path.join(app.static_folder, 'images', 'FondoCotizacion.png')
            fondo_base64 = ""
            if os.path.exists(fondo_path):
                try:
                    with open(fondo_path, "rb") as image_file:
                        fondo_base64 = f"data:image/png;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"
                except Exception:
                    pass

            # Construir datos de cliente seleccionado si existe
            cliente_data = {
                'nombre': nombre_cliente,
                'telefono': "S/N",
                'email': "S/N",
                'nit': "S/N"
            }
        
            if cliente_id:
                try:
                    conn_c = get_db_connection()
                    cur_c = conn_c.cursor()
                    cur_c.execute('SELECT nombre, nit, telefono, correo FROM clientes WHERE id = ?', (cliente_id,))
                    crow = cur_c.fetchone()
                    conn_c.close()
                    if crow:
                        cliente_data['nombre'] = crow[0] or cliente_data['nombre']
                        cliente_data['nit'] = crow[1] or "S/N"
                        cliente_data['telefono'] = crow[2] or "S/N"
                        cliente_data['email'] = crow[3] or "S/N"
                except Exception:
                    pass

            # Construir datos de usuario
            usuario = {
                'nombre': session.get('user_nombre', 'Usuario del sistema'),
                'telefono': session.get('user_telefono', None),
                'email': session.get('user_email', None)
            }
            if not usuario.get('telefono') and session.get('user_id'):
                try:
                    conn_u = get_db_connection()
                    cur_u = conn_u.cursor()
                    cur_u.execute('SELECT nombre, telefono, correo FROM clientes WHERE id = ?', (session.get('user_id'),))
                    urow = cur_u.fetchone()
                    conn_u.close()
                    if urow:
                        usuario['nombre'] = urow[0] or usuario['nombre']
                        usuario['telefono'] = urow[1] or usuario['telefono']
                        usuario['email'] = urow[2] or usuario['email']
                except Exception:
                    pass

            productos_formateados = []
            for item in items:
                qty = float(item.get('cantidad', 0))
                price = float(item.get('precio_unitario', 0.0))
                productos_formateados.append({
                    'codigo': item.get('codigo', 'S/N'),
                    'descripcion': item.get('descripcion', 'Producto'),
                    'marca': item.get('marca', 'S/M'),
                    'procedencia': item.get('procedencia', 'Taiwán'),
                    'cantidad': qty,
                    'um': item.get('um', 'UN'),
                    'precio_unitario': price,
                    'subtotal': qty * price
                })

            from models import obtener_configuracion_pdf
            config_pdf = obtener_configuracion_pdf(session.get('user_id'))

            datos = {
                'cliente': cliente_data,
                'cotizacion': {
                    'solicitud_numero': "Directo",
                    'fecha': fecha_cotizacion,
                },
                'productos': productos_formateados,
                'subtotal': subtotal_bruto,
                'descuento': f"{descuento_porcentaje:.2f}",
                'descuento_porcentaje': descuento_porcentaje,
                'monto_descuento': monto_descuento,
                'total': total_final,
                'total_letras': total_letras,
                'usuario_sesion': session.get('user_nombre', 'Usuario del sistema'),
                'usuario': usuario,
                'logo_base64': "",
                'fondo_base64': None,  # El fondo se aplicará por página después con PyPDF2
                'es_pdf': True,
                'config_pdf': config_pdf
            }

            # Generar el HTML
            html_renderizado = render_template('cotizaciones/cotizacion_pdf.html', **datos)
        
            # Buscar path de wkhtmltopdf
            wkhtmltopdf_path = None
            if os.name == "nt":
                possible_paths = [
                    r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
                    r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        wkhtmltopdf_path = path
                        break
            else:
                import subprocess
                try:
                    wkhtmltopdf_path = subprocess.check_output(['which', 'wkhtmltopdf']).decode().strip()
                except:
                    wkhtmltopdf_path = '/usr/local/bin/wkhtmltopdf'

            # Generar PDF real usando la lógica de wkhtmltopdf y PyPDF2 (idéntica a pdf_cotizacion)
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
            options = {
                'page-size': 'Letter',
                'enable-local-file-access': None,
                'encoding': 'UTF-8',
                'quiet': '',
                'margin-top': '10mm',
                'margin-right': '10mm',
                'margin-bottom': '10mm',
                'margin-left': '10mm',
            }

            try:
                # Generar PDF base (como el usuario quiere hoja blanca, no aplicamos fondos)
                pdf_sin_fondo = pdfkit.from_string(html_renderizado, False, configuration=config, options=options)
                
                # El usuario solicitó específicamente una hoja blanca para el PDF Directo,
                # así que omitimos la lógica de PyPDF2 y devolvemos directamente el pdf de wkhtmltopdf
                pdf_final = pdf_sin_fondo

                response = make_response(pdf_final)
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = 'inline; filename=cotizacion_directa.pdf'
                return response
            
            except OSError as e:
                print(f"Error con wkhtmltopdf en PDF Directo: {e}")
                return f"Error al generar PDF: No se encontró wkhtmltopdf", 500

        except Exception as e:
            print(f"Error general en PDF directo: {e}")
            if request.is_json:
                return jsonify({'success': False, 'message': str(e)})
            else:
                return f"Error generando PDF: {str(e)}", 500

    @app.route('/api/empresa/campos-config', methods=['GET', 'POST'], strict_slashes=False)
    @app.route('/api/empresa/campos-config/', methods=['GET', 'POST'], strict_slashes=False)
    @login_required
    def api_campos_config():
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            
            admin_id = user_id
            if user_rol != 'admin' and user_rol != 'superadmin':
                cursor.execute("SELECT creador_id FROM clientes WHERE id = ?", (user_id,))
                res = cursor.fetchone()
                if res and res[0]:
                    admin_id = res[0]

            if request.method == 'POST':
                data = request.get_json(silent=True) or {}
                campos_list = data.get('campos', [])
                campos_json = json.dumps(campos_list, ensure_ascii=False)
                
                cursor.execute("UPDATE clientes SET campos_config = ? WHERE id = ?", (campos_json, admin_id))
                conexion.commit()
                return jsonify({'success': True, 'message': 'Configuración de campos guardada con éxito', 'campos': campos_list})

            cursor.execute("SELECT campos_config FROM clientes WHERE id = ?", (admin_id,))
            res = cursor.fetchone()
            campos_config = []
            if res and res[0]:
                try:
                    campos_config = json.loads(res[0])
                except Exception:
                    campos_config = []
            
            return jsonify({'success': True, 'campos': campos_config})

