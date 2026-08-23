from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import sqlite3
import json
import os
from db_wrapper import get_db_connection
from utils.decorators import login_required, admin_required
from models import registrar_log

def _obtener_info_tenant_proveedor(cursor, user_id, user_rol):
    """Devuelve (owner_id, empresa_nombre) para aislamiento multi-tenant de proveedores"""
    if user_rol == 'superadmin':
        return None, 'General'

    cursor.execute("SELECT id, nombre, empresa_nombre, creador_id, rol FROM clientes WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    if not u:
        return user_id, 'General'

    nombre = u['nombre'] if hasattr(u, 'keys') else u[1]
    empresa_nom = u['empresa_nombre'] if hasattr(u, 'keys') else u[2]
    creador_id = u['creador_id'] if hasattr(u, 'keys') else u[3]
    rol = u['rol'] if hasattr(u, 'keys') else u[4]

    owner_id = user_id
    empresa_final = empresa_nom or nombre or 'General'

    if rol == 'standard' and creador_id:
        owner_id = creador_id
        cursor.execute("SELECT nombre, empresa_nombre FROM clientes WHERE id = ?", (creador_id,))
        p = cursor.fetchone()
        if p:
            p_emp = p['empresa_nombre'] if hasattr(p, 'keys') else p[1]
            p_nom = p['nombre'] if hasattr(p, 'keys') else p[0]
            empresa_final = p_emp or p_nom or 'General'

    return owner_id, empresa_final.strip()

def register_routes(app):
    @app.route('/proveedores', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def proveedores():
        mensaje_error = None
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            owner_id, empresa_usuario = _obtener_info_tenant_proveedor(cursor, user_id, user_rol)

        if request.method == 'POST':
            try:
                nombre = request.form.get('nombre', '').strip()
                nit_ruc = request.form.get('nit_ruc', '').strip()
                contacto_nombre = request.form.get('contacto_nombre', '').strip()
                telefono = request.form.get('telefono', '').strip()
                correo = request.form.get('correo', '').strip()
                direccion = request.form.get('direccion', '').strip()
                rubro = request.form.get('rubro', '').strip()

                if not nombre:
                    flash('La Razón Social / Nombre es obligatoria.', 'warning')
                else:
                    if not contacto_nombre:
                        contacto_nombre = 'N/A'
                    with get_db_connection() as conexion:
                        cursor = conexion.cursor()
                        # Validar duplicados dentro de la empresa
                        if user_rol == 'superadmin':
                            cursor.execute("SELECT COUNT(*) FROM proveedores WHERE LOWER(nombre) = LOWER(?)", (nombre,))
                        else:
                            cursor.execute("SELECT COUNT(*) FROM proveedores WHERE (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL) AND LOWER(nombre) = LOWER(?)", 
                                           (user_id, owner_id, empresa_usuario, nombre))
                        if cursor.fetchone()[0] > 0:
                            flash(f'⚠️ El proveedor "{nombre}" ya se encuentra registrado en tu empresa.', 'warning')
                        else:
                            emp_to_save = empresa_usuario or 'General'
                            cursor.execute('''
                                INSERT INTO proveedores (empresa, nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, creador_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (emp_to_save, nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, user_id))
                            nuevo_prov_id = cursor.lastrowid
                            conexion.commit()

                            registrar_log(
                                usuario_id=user_id,
                                accion="crear_proveedor",
                                detalle={"proveedor_id": nuevo_prov_id, "nombre": nombre, "empresa": emp_to_save}
                            )

                            flash(f'¡Proveedor "{nombre}" registrado exitosamente!', 'success')
                            return redirect(url_for('proveedores'))
            except Exception as e:
                flash(f'Error al registrar proveedor: {str(e)}', 'danger')

        # Parámetros de búsqueda y paginación
        query_search = request.args.get('q', '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 8))
        offset = (page - 1) * per_page

        proveedores_lista = []
        total_items = 0
        total_pages = 1

        try:
            with get_db_connection() as conexion:
                conexion.row_factory = sqlite3.Row
                cursor = conexion.cursor()

                if user_rol == 'superadmin':
                    base_sql = "FROM proveedores WHERE 1=1"
                    params = []
                else:
                    base_sql = "FROM proveedores WHERE (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL)"
                    params = [user_id, owner_id, empresa_usuario]

                if query_search:
                    base_sql += " AND (LOWER(nombre) LIKE LOWER(?) OR LOWER(nit_ruc) LIKE LOWER(?) OR LOWER(contacto_nombre) LIKE LOWER(?) OR LOWER(rubro) LIKE LOWER(?))"
                    p_search = f"%{query_search}%"
                    params.extend([p_search, p_search, p_search, p_search])

                cursor.execute(f"SELECT COUNT(*) {base_sql}", params)
                total_items = cursor.fetchone()[0]
                total_pages = max(1, (total_items + per_page - 1) // per_page)

                cursor.execute(f"SELECT * {base_sql} ORDER BY id DESC LIMIT ? OFFSET ?", params + [per_page, offset])
                proveedores_lista = [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            mensaje_error = f"Error al cargar proveedores: {str(e)}"

        pagination = {
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'total_items': total_items
        }

        return render_template(
            'proveedores/proveedores.html',
            proveedores=proveedores_lista,
            pagination=pagination,
            query_search=query_search,
            mensaje_error=mensaje_error
        )

    @app.route('/proveedores/editar/<int:id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def editar_proveedor(id):
        if request.method == 'GET':
            return redirect(url_for('proveedores'))

        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        try:
            nombre = request.form.get('nombre', '').strip()
            nit_ruc = request.form.get('nit_ruc', '').strip()
            contacto_nombre = request.form.get('contacto_nombre', '').strip()
            telefono = request.form.get('telefono', '').strip()
            correo = request.form.get('correo', '').strip()
            direccion = request.form.get('direccion', '').strip()
            rubro = request.form.get('rubro', '').strip()

            if not nombre:
                flash('La Razón Social / Nombre es obligatoria.', 'warning')
                return redirect(url_for('proveedores'))

            if not contacto_nombre:
                contacto_nombre = 'N/A'

            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                owner_id, empresa_usuario = _obtener_info_tenant_proveedor(cursor, user_id, user_rol)

                # 1. Validar propiedad del proveedor (Anti-IDOR)
                cursor.execute("SELECT nombre, empresa, creador_id FROM proveedores WHERE id = ?", (id,))
                prov_anterior = cursor.fetchone()
                if not prov_anterior:
                    flash('El proveedor no existe.', 'danger')
                    return redirect(url_for('proveedores'))

                prov_nombre = prov_anterior[0]
                prov_emp = prov_anterior[1]
                prov_creador = prov_anterior[2]

                if user_rol != 'superadmin' and prov_creador not in [user_id, owner_id] and prov_emp != empresa_usuario and prov_emp != 'General' and prov_creador is not None:
                    flash('No tienes permisos para editar este proveedor.', 'danger')
                    return redirect(url_for('proveedores'))

                nombre_anterior = prov_nombre

                # 2. Actualizar proveedor
                cursor.execute('''
                    UPDATE proveedores 
                    SET nombre=?, nit_ruc=?, contacto_nombre=?, telefono=?, correo=?, direccion=?, rubro=?
                    WHERE id=?
                ''', (nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, id))

                # 3. Cascada: Actualizar el nombre en productos de esta empresa
                if nombre_anterior and nombre != nombre_anterior:
                    try:
                        cursor.execute("PRAGMA table_info(productos)")
                        cols_prod = [c[1] for c in cursor.fetchall()]
                        if 'proveedor_id' in cols_prod:
                            if user_rol == 'superadmin':
                                cursor.execute('''
                                    UPDATE productos
                                    SET proveedor = ?, proveedor_id = ?
                                    WHERE proveedor_id = ? OR LOWER(proveedor) = LOWER(?)
                                ''', (nombre, id, id, nombre_anterior))
                            else:
                                cursor.execute('''
                                    UPDATE productos
                                    SET proveedor = ?, proveedor_id = ?
                                    WHERE (proveedor_id = ? OR LOWER(proveedor) = LOWER(?))
                                      AND (empresa = ? OR empresa = 'General')
                                ''', (nombre, id, id, nombre_anterior, empresa_usuario))
                        else:
                            if user_rol == 'superadmin':
                                cursor.execute('''
                                    UPDATE productos
                                    SET proveedor = ?
                                    WHERE LOWER(proveedor) = LOWER(?)
                                ''', (nombre, nombre_anterior))
                            else:
                                cursor.execute('''
                                    UPDATE productos
                                    SET proveedor = ?
                                    WHERE LOWER(proveedor) = LOWER(?)
                                      AND (empresa = ? OR empresa = 'General')
                                ''', (nombre, nombre_anterior, empresa_usuario))
                    except Exception as e_casc:
                        print(f"[WARN] Error actualizando productos asociados: {e_casc}")

                conexion.commit()

                registrar_log(
                    usuario_id=user_id,
                    accion="editar_proveedor",
                    detalle={"proveedor_id": id, "nombre_nuevo": nombre, "nombre_anterior": nombre_anterior}
                )

                flash(f'¡Proveedor "{nombre}" y sus productos asociados actualizados correctamente!', 'success')
        except Exception as e:
            flash(f'Error al actualizar proveedor: {str(e)}', 'danger')

        return redirect(url_for('proveedores'))

    @app.route('/proveedores/eliminar/<int:id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def eliminar_proveedor(id):
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                owner_id, empresa_usuario = _obtener_info_tenant_proveedor(cursor, user_id, user_rol)

                cursor.execute("SELECT id, nombre, empresa, creador_id FROM proveedores WHERE id = ?", (id,))
                prov = cursor.fetchone()
                if not prov:
                    flash('Proveedor no encontrado.', 'danger')
                    return redirect(url_for('proveedores'))

                prov_nombre = prov[1]
                prov_emp = prov[2]
                prov_creador = prov[3]

                if user_rol != 'superadmin' and prov_creador not in [user_id, owner_id] and prov_emp != empresa_usuario and prov_emp != 'General' and prov_creador is not None:
                    flash('No tienes permisos para eliminar este proveedor.', 'danger')
                    return redirect(url_for('proveedores'))

                # Desvincular productos antes de eliminar (limpieza de huérfanos)
                try:
                    cursor.execute("UPDATE productos SET proveedor_id = NULL WHERE proveedor_id = ?", (id,))
                except Exception as e_unl:
                    print(f"[WARN] Error desvinculando productos de proveedor {id}: {e_unl}")

                cursor.execute("DELETE FROM proveedores WHERE id=?", (id,))
                conexion.commit()

                registrar_log(
                    usuario_id=user_id,
                    accion="eliminar_proveedor",
                    detalle={"proveedor_id": id, "nombre": prov_nombre}
                )

                flash(f'Proveedor "{prov_nombre}" eliminado exitosamente.', 'success')
        except Exception as e:
            flash(f'Error al eliminar proveedor: {str(e)}', 'danger')

        return redirect(url_for('proveedores'))

    @app.route('/api/proveedores/buscar', methods=['GET'])
    @login_required
    def api_buscar_proveedores():
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        query_search = request.args.get('q', '').strip()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            per_page = int(request.args.get('per_page', 5))
        except (ValueError, TypeError):
            per_page = 5
        if per_page not in [5, 15, 30]:
            per_page = 5

        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            owner_id, empresa_usuario = _obtener_info_tenant_proveedor(cursor, user_id, user_rol)

            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            if user_rol == 'superadmin':
                base_sql = "FROM proveedores WHERE 1=1"
                params = []
            else:
                base_sql = "FROM proveedores WHERE (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL)"
                params = [user_id, owner_id, empresa_usuario]

            if query_search:
                base_sql += " AND (LOWER(nombre) LIKE LOWER(?) OR LOWER(nit_ruc) LIKE LOWER(?) OR LOWER(contacto_nombre) LIKE LOWER(?) OR LOWER(rubro) LIKE LOWER(?))"
                p_search = f"%{query_search}%"
                params.extend([p_search, p_search, p_search, p_search])

            cursor.execute(f"SELECT COUNT(*) {base_sql}", params)
            total_items = cursor.fetchone()[0]
            total_pages = max(1, (total_items + per_page - 1) // per_page)
            if page > total_pages:
                page = total_pages
            offset = max(0, (page - 1) * per_page)

            cursor.execute(f"SELECT * {base_sql} ORDER BY id DESC LIMIT ? OFFSET ?", params + [per_page, offset])
            rows = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'proveedores': rows,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'total_items': total_items
                }
            })

    @app.route('/api/proveedores', methods=['GET'])
    @login_required
    def api_proveedores():
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            owner_id, empresa_usuario = _obtener_info_tenant_proveedor(cursor, user_id, user_rol)

            if user_rol == 'superadmin':
                cursor.execute("SELECT id, nombre, nit_ruc, contacto_nombre, telefono FROM proveedores ORDER BY nombre ASC")
            else:
                cursor.execute("""
                    SELECT id, nombre, nit_ruc, contacto_nombre, telefono 
                    FROM proveedores 
                    WHERE (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL)
                    ORDER BY nombre ASC
                """, (user_id, owner_id, empresa_usuario))

            rows = [dict(r) for r in cursor.fetchall()]
            return jsonify({'success': True, 'proveedores': rows})
