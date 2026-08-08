from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import sqlite3
import json
import os
from db_wrapper import get_db_connection
from utils.decorators import login_required, admin_required

def register_routes(app):
    @app.route('/proveedores', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def proveedores():
        mensaje_error = None
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        
        # Determinar empresa/creador_id del usuario
        with get_db_connection() as conexion:
            cursor = conexion.cursor()
            cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (user_id,))
            u = cursor.fetchone()
            empresa_usuario = u[0] if u and u[0] else (u[1] if u and u[1] else 'General')

        if request.method == 'POST':
            try:
                nombre = request.form.get('nombre', '').strip()
                nit_ruc = request.form.get('nit_ruc', '').strip()
                contacto_nombre = request.form.get('contacto_nombre', '').strip()
                telefono = request.form.get('telefono', '').strip()
                correo = request.form.get('correo', '').strip()
                direccion = request.form.get('direccion', '').strip()
                rubro = request.form.get('rubro', '').strip()

                if not nombre or not contacto_nombre:
                    flash('La Razón Social/Nombre y el Asesor/Contacto son obligatorios.', 'warning')
                else:
                    with get_db_connection() as conexion:
                        cursor = conexion.cursor()
                        # Validar si ya existe
                        cursor.execute("SELECT COUNT(*) FROM proveedores WHERE empresa = ? AND nombre = ?", (empresa_usuario, nombre))
                        if cursor.fetchone()[0] > 0:
                            flash(f'⚠️ El proveedor "{nombre}" ya se encuentra registrado.', 'warning')
                        else:
                            cursor.execute('''
                                INSERT INTO proveedores (empresa, nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, creador_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (empresa_usuario, nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, user_id))
                            conexion.commit()
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

                base_sql = "FROM proveedores WHERE (creador_id = ? OR empresa = ?)"
                params = [user_id, empresa_usuario]

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

    @app.route('/proveedores/editar/<int:id>', methods=['POST'])
    @login_required
    @admin_required
    def editar_proveedor(id):
        try:
            nombre = request.form.get('nombre', '').strip()
            nit_ruc = request.form.get('nit_ruc', '').strip()
            contacto_nombre = request.form.get('contacto_nombre', '').strip()
            telefono = request.form.get('telefono', '').strip()
            correo = request.form.get('correo', '').strip()
            direccion = request.form.get('direccion', '').strip()
            rubro = request.form.get('rubro', '').strip()

            if not nombre or not contacto_nombre:
                flash('La Razón Social/Nombre y el Asesor/Contacto son obligatorios.', 'warning')
                return redirect(url_for('proveedores'))

            with get_db_connection() as conexion:
                cursor = conexion.cursor()

                # 1. Obtener el nombre anterior del proveedor
                cursor.execute("SELECT nombre, empresa FROM proveedores WHERE id = ?", (id,))
                prov_anterior = cursor.fetchone()
                nombre_anterior = prov_anterior[0] if prov_anterior else None

                # 2. Actualizar proveedor
                cursor.execute('''
                    UPDATE proveedores 
                    SET nombre=?, nit_ruc=?, contacto_nombre=?, telefono=?, correo=?, direccion=?, rubro=?
                    WHERE id=?
                ''', (nombre, nit_ruc, contacto_nombre, telefono, correo, direccion, rubro, id))

                # 3. Cascada: Actualizar el nombre en todos los productos que usaban el proveedor anterior
                if nombre_anterior and nombre != nombre_anterior:
                    try:
                        cursor.execute("PRAGMA table_info(productos)")
                        cols_prod = [c[1] for c in cursor.fetchall()]
                        if 'proveedor_id' in cols_prod:
                            cursor.execute('''
                                UPDATE productos
                                SET proveedor = ?
                                WHERE proveedor_id = ? OR LOWER(proveedor) = LOWER(?)
                            ''', (nombre, id, nombre_anterior))
                        else:
                            cursor.execute('''
                                UPDATE productos
                                SET proveedor = ?
                                WHERE LOWER(proveedor) = LOWER(?)
                            ''', (nombre, nombre_anterior))
                    except Exception as e_casc:
                        print(f"[WARN] Error actualizando productos asociados: {e_casc}")

                conexion.commit()
                flash(f'¡Proveedor "{nombre}" y sus productos asociados actualizados correctamente!', 'success')
        except Exception as e:
            flash(f'Error al actualizar proveedor: {str(e)}', 'danger')

        return redirect(url_for('proveedores'))

    @app.route('/proveedores/eliminar/<int:id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def eliminar_proveedor(id):
        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                cursor.execute("DELETE FROM proveedores WHERE id=?", (id,))
                conexion.commit()
                flash('Proveedor eliminado exitosamente', 'success')
        except Exception as e:
            flash(f'Error al eliminar proveedor: {str(e)}', 'danger')

        return redirect(url_for('proveedores'))

    @app.route('/api/proveedores/buscar', methods=['GET'])
    @login_required
    def api_buscar_proveedores():
        user_id = session.get('user_id')
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
            cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (user_id,))
            u = cursor.fetchone()
            empresa_usuario = u[0] if u and u[0] else (u[1] if u and u[1] else 'General')

            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()

            base_sql = "FROM proveedores WHERE (creador_id = ? OR empresa = ?)"
            params = [user_id, empresa_usuario]

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
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute("SELECT id, nombre, nit_ruc, contacto_nombre, telefono FROM proveedores ORDER BY nombre ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            return jsonify({'success': True, 'proveedores': rows})
