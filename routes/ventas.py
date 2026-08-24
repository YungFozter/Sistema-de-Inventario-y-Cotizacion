from flask import Flask, flash, render_template, request, redirect, session, url_for, make_response, jsonify
import sqlite3
import os
import json
from datetime import datetime
from db_wrapper import get_db_connection
from models import registrar_log, obtener_fecha_bolivia
from utils.decorators import login_required, admin_required
from utils.helpers import format_date

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


def _validar_acceso_venta(cursor, venta_id, user_id, user_rol):
    """Verifica si el usuario actual tiene permisos para acceder a una venta específica (Anti-IDOR)"""
    if user_rol == 'superadmin':
        return True
    
    cursor.execute("""
        SELECT v.id, v.creador_id, v.vendedor_id
        FROM ventas v
        WHERE v.id = ?
    """, (venta_id,))
    row = cursor.fetchone()
    if not row:
        return False
    
    creador_id = row['creador_id'] if hasattr(row, 'keys') else row[1]
    vendedor_id = row['vendedor_id'] if hasattr(row, 'keys') else row[2]
    
    admin_owner_id = session.get('creador_id') or user_id
    
    # 1. Si es el creador/dueño o el vendedor que realizó la venta
    if user_id in (creador_id, vendedor_id) or admin_owner_id == creador_id:
        return True
        
    return False


def register_routes(app):
    @app.route('/ventas', methods=['GET'])
    @login_required
    def ventas_pos():
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        admin_owner_id = session.get('creador_id') or user_id

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            # 1. Obtener categorías activas
            cursor.execute("SELECT id, nombre FROM categorias WHERE activo = 1 ORDER BY nombre")
            categorias = cursor.fetchall()

            # 2. Obtener lista de clientes para la venta (incluye opción cliente contado)
            if user_rol == 'superadmin':
                cursor.execute("SELECT id, nombre, nit, codigo_cliente, telefono FROM clientes WHERE rol = 'cliente' ORDER BY nombre")
            else:
                cursor.execute("""
                    SELECT id, nombre, nit, codigo_cliente, telefono 
                    FROM clientes 
                    WHERE (creador_id = ? OR creador_id = ?) AND rol = 'cliente' 
                    ORDER BY nombre
                """, (admin_owner_id, user_id))
            clientes = cursor.fetchall()

            # 3. Obtener catálogo de productos del tenant
            empresa_nombre = _obtener_empresa_usuario(cursor, user_id, user_rol)
            if user_rol == 'superadmin':
                cursor.execute("""
                    SELECT id, empresa, codigo, descripcion, marca, tm, um, cantidad, stock_reservado, precio_unitario, categoria
                    FROM productos 
                    WHERE (activo IS TRUE OR activo = 1 OR activo IS NULL)
                    ORDER BY descripcion ASC
                """)
            else:
                cursor.execute("""
                    SELECT id, empresa, codigo, descripcion, marca, tm, um, cantidad, stock_reservado, precio_unitario, categoria
                    FROM productos 
                    WHERE (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL)
                      AND (activo IS TRUE OR activo = 1 OR activo IS NULL)
                    ORDER BY descripcion ASC
                """, (user_id, admin_owner_id, empresa_nombre))
            productos = cursor.fetchall()

            # 4. Obtener historial reciente de ventas (últimas 20)
            if user_rol == 'superadmin':
                cursor.execute("""
                    SELECT v.id, v.codigo_venta, v.fecha, v.total, v.metodo_pago, v.estado_pago, 
                           COALESCE(c.nombre, 'Cliente General / Mostrador') as cliente_nombre,
                           u.nombre as vendedor_nombre
                    FROM ventas v
                    LEFT JOIN clientes c ON v.cliente_id = c.id
                    LEFT JOIN clientes u ON v.vendedor_id = u.id
                    ORDER BY v.fecha DESC LIMIT 20
                """)
            else:
                cursor.execute("""
                    SELECT v.id, v.codigo_venta, v.fecha, v.total, v.metodo_pago, v.estado_pago, 
                           COALESCE(c.nombre, 'Cliente General / Mostrador') as cliente_nombre,
                           u.nombre as vendedor_nombre
                    FROM ventas v
                    LEFT JOIN clientes c ON v.cliente_id = c.id
                    LEFT JOIN clientes u ON v.vendedor_id = u.id
                    WHERE v.creador_id = ? OR v.vendedor_id = ?
                    ORDER BY v.fecha DESC LIMIT 20
                """, (admin_owner_id, user_id))
            ventas_recientes = cursor.fetchall()

            return render_template(
                'ventas/ventas.html',
                categorias=categorias,
                clientes=clientes,
                productos=productos,
                ventas_recientes=ventas_recientes
            )

        except Exception as e:
            app.logger.error(f"Error al cargar módulo de Ventas POS: {e}")
            flash(f"Error al cargar pantalla de Ventas: {str(e)}", "danger")
            return redirect(url_for('dashboard') if user_rol in ['admin', 'superadmin'] else url_for('standard_dashboard'))
        finally:
            conexion.close()


    @app.route('/api/ventas/guardar', methods=['POST'])
    @login_required
    def guardar_venta_api():
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')
        admin_owner_id = session.get('creador_id') or user_id

        data = request.get_json(silent=True) or request.form

        # Extraer parámetros
        cliente_id_raw = data.get('cliente_id')
        cliente_id = int(cliente_id_raw) if cliente_id_raw and str(cliente_id_raw).isdigit() and int(cliente_id_raw) > 0 else None
        metodo_pago = data.get('metodo_pago', 'efectivo').strip().lower()
        if metodo_pago not in ['efectivo', 'transferencia', 'qr', 'tarjeta', 'credito']:
            metodo_pago = 'efectivo'

        # Validar y restringir descuento
        try:
            descuento_porcentaje = max(0.0, min(100.0, float(data.get('descuento_porcentaje', 0.0) or 0.0)))
        except (ValueError, TypeError):
            descuento_porcentaje = 0.0
        notas = data.get('notas', '').strip()

        # Extraer items del carrito
        items_raw = data.get('items', [])
        if isinstance(items_raw, str):
            try:
                items_raw = json.loads(items_raw)
            except Exception:
                items_raw = []

        if not items_raw:
            return jsonify({'success': False, 'message': 'El carrito de ventas está vacío'}), 400

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            empresa_nombre = _obtener_empresa_usuario(cursor, user_id, user_rol)

            # Iniciar transacción
            is_postgres = bool(not os.environ.get('TESTING_DB') and os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith('postgres'))
            if not is_postgres:
                cursor.execute("BEGIN IMMEDIATE TRANSACTION")

            # 0. Validar pertenencia del cliente (Anti-IDOR)
            if cliente_id:
                if user_rol == 'superadmin':
                    cursor.execute("SELECT id FROM clientes WHERE id = ? AND rol = 'cliente'", (cliente_id,))
                else:
                    cursor.execute("""
                        SELECT id FROM clientes 
                        WHERE id = ? AND rol = 'cliente' 
                          AND (creador_id = ? OR creador_id = ?)
                    """, (cliente_id, admin_owner_id, user_id))
                if not cursor.fetchone():
                    conexion.rollback()
                    return jsonify({'success': False, 'message': 'El cliente seleccionado no existe o no pertenece a tu empresa'}), 403

            # 1. Validar productos con aislamiento multi-tenant y verificar stock disponible al instante
            productos_para_venta = []
            subtotal_bruto = 0.0

            for item in items_raw:
                try:
                    prod_id = int(item.get('producto_id', 0))
                    cant = int(item.get('cantidad', 1))
                    precio = float(item.get('precio_unitario', 0.0))
                except (ValueError, TypeError):
                    conexion.rollback()
                    return jsonify({'success': False, 'message': 'Formato numérico inválido en los datos de venta'}), 400

                if cant <= 0 or precio < 0:
                    conexion.rollback()
                    return jsonify({'success': False, 'message': 'Cantidad o precio inválido en los productos seleccionados'}), 400

                # Validar existencia de producto dentro del Tenant autorizado
                if user_rol == 'superadmin':
                    cursor.execute("""
                        SELECT id, codigo, descripcion, cantidad, stock_reservado, precio_unitario 
                        FROM productos 
                        WHERE id = ? AND (activo IS TRUE OR activo = 1 OR activo IS NULL)
                    """, (prod_id,))
                else:
                    cursor.execute("""
                        SELECT id, codigo, descripcion, cantidad, stock_reservado, precio_unitario 
                        FROM productos 
                        WHERE id = ? 
                          AND (creador_id = ? OR creador_id = ? OR empresa = ? OR empresa = 'General' OR creador_id IS NULL)
                          AND (activo IS TRUE OR activo = 1 OR activo IS NULL)
                    """, (prod_id, user_id, admin_owner_id, empresa_nombre))

                prod = cursor.fetchone()

                if not prod:
                    conexion.rollback()
                    return jsonify({'success': False, 'message': f'Producto ID #{prod_id} no disponible o no pertenece a tu empresa'}), 404

                # Protección contra manipulación de precios por vendedores standard
                precio_catalogo = float(prod['precio_unitario'] or 0.0)
                if user_rol == 'standard' and precio < precio_catalogo:
                    precio = precio_catalogo

                stock_fisico = float(prod['cantidad']) if prod['cantidad'] is not None else 0.0
                stock_reserv = float(prod['stock_reservado']) if prod['stock_reservado'] is not None else 0.0
                stock_disponible = max(0.0, stock_fisico - stock_reserv)

                # Superadmin ignora restricción estricta de stock
                if user_rol != 'superadmin' and cant > stock_disponible:
                    conexion.rollback()
                    return jsonify({
                        'success': False, 
                        'message': f"Stock insuficiente para '{prod['descripcion']}' ({prod['codigo']}). Disponible: {int(stock_disponible)}, Solicitado: {cant}"
                    }), 400

                subtot_item = cant * precio
                subtotal_bruto += subtot_item
                productos_para_venta.append({
                    'producto_id': prod_id,
                    'cantidad': cant,
                    'precio_unitario': precio,
                    'subtotal': subtot_item,
                    'descripcion': prod['descripcion']
                })

            # 2. Calcular montos finales
            descuento_monto = round(subtotal_bruto * (descuento_porcentaje / 100.0), 2)
            total_final = max(0.0, round(subtotal_bruto - descuento_monto, 2))

            # 3. Generar código correlativo de venta
            fecha_ahora = obtener_fecha_bolivia().strftime('%Y-%m-%d %H:%M:%S')
            prefix_anio = datetime.now().strftime('%Y')
            
            cursor.execute("SELECT COUNT(*) FROM ventas WHERE creador_id = ?", (admin_owner_id,))
            num_ventas = cursor.fetchone()[0] + 1
            codigo_venta = f"VNT-{prefix_anio}-{num_ventas:05d}"

            # 4. Insertar registro de venta cabecera
            cursor.execute("""
                INSERT INTO ventas 
                (codigo_venta, cliente_id, vendedor_id, creador_id, empresa, fecha, subtotal, descuento_porcentaje, descuento_monto, total, metodo_pago, estado_pago, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pagado', ?)
            """, (codigo_venta, cliente_id, user_id, admin_owner_id, empresa_nombre, fecha_ahora, subtotal_bruto, descuento_porcentaje, descuento_monto, total_final, metodo_pago, notas))

            if is_postgres:
                cursor.execute("SELECT currval(pg_get_serial_sequence('ventas', 'id'))")
                venta_id = cursor.fetchone()[0]
            else:
                venta_id = cursor.lastrowid

            # 5. Insertar items y DESCONTAR INVENTARIO FÍSICO ATÓMICAMENTE
            for p in productos_para_venta:
                cursor.execute("""
                    INSERT INTO venta_productos (venta_id, producto_id, cantidad, precio_unitario, subtotal, descuento)
                    VALUES (?, ?, ?, ?, ?, 0.0)
                """, (venta_id, p['producto_id'], p['cantidad'], p['precio_unitario'], p['subtotal']))

                # Deducción atómica con verificación concurrente
                if user_rol == 'superadmin':
                    cursor.execute("""
                        UPDATE productos 
                        SET cantidad = CASE WHEN cantidad - ? < 0 THEN 0 ELSE cantidad - ? END,
                            fecha_actualizacion = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (p['cantidad'], p['cantidad'], p['producto_id']))
                else:
                    cursor.execute("""
                        UPDATE productos 
                        SET cantidad = cantidad - ?,
                            fecha_actualizacion = CURRENT_TIMESTAMP
                        WHERE id = ? AND (cantidad - COALESCE(stock_reservado, 0)) >= ?
                    """, (p['cantidad'], p['producto_id'], p['cantidad']))

                    if cursor.rowcount == 0:
                        conexion.rollback()
                        return jsonify({
                            'success': False, 
                            'message': f"Conflicto de stock concurrente para '{p['descripcion']}'. Operación revertida."
                        }), 409

            conexion.commit()

            # 6. Registrar en el log de auditoría
            registrar_log(
                usuario_id=user_id,
                accion="crear_venta",
                detalle={
                    "venta_id": venta_id,
                    "codigo_venta": codigo_venta,
                    "total": total_final,
                    "items": len(productos_para_venta),
                    "metodo_pago": metodo_pago
                }
            )

            return jsonify({
                'success': True,
                'message': f'Venta {codigo_venta} realizada exitosamente.',
                'venta_id': venta_id,
                'codigo_venta': codigo_venta,
                'total': total_final,
                'comprobante_url': url_for('ver_comprobante_venta', id=venta_id)
            })

        except Exception as e:
            conexion.rollback()
            app.logger.error(f"Error al guardar venta API: {e}")
            return jsonify({'success': False, 'message': f'Error procesando venta: {str(e)}'}), 500
        finally:
            conexion.close()


    @app.route('/ventas/<int:id>/comprobante')
    @login_required
    def ver_comprobante_venta(id):
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            if not _validar_acceso_venta(cursor, id, user_id, user_rol):
                flash("No tienes permisos para ver este comprobante de venta.", "danger")
                return redirect(url_for('ventas_pos'))

            cursor.execute("""
                SELECT v.id, v.codigo_venta, v.fecha, v.subtotal, v.descuento_porcentaje, v.descuento_monto, v.total, 
                       v.metodo_pago, v.estado_pago, v.notas, v.empresa,
                       COALESCE(c.nombre, 'Cliente General / Mostrador') as cliente_nombre,
                       COALESCE(c.nit, 'N/A') as cliente_nit,
                       COALESCE(c.telefono, 'N/A') as cliente_telefono,
                       COALESCE(c.referencia, '') as cliente_direccion,
                       u.nombre as vendedor_nombre
                FROM ventas v
                LEFT JOIN clientes c ON v.cliente_id = c.id
                LEFT JOIN clientes u ON v.vendedor_id = u.id
                WHERE v.id = ?
            """, (id,))
            venta = cursor.fetchone()

            if not venta:
                flash("Venta no encontrada.", "danger")
                return redirect(url_for('ventas_pos'))

            cursor.execute("""
                SELECT vp.cantidad, vp.precio_unitario, vp.subtotal,
                       p.codigo, p.descripcion, p.um
                FROM venta_productos vp
                JOIN productos p ON vp.producto_id = p.id
                WHERE vp.venta_id = ?
            """, (id,))
            items = cursor.fetchall()

            # Obtener datos de la empresa emisora
            cursor.execute("SELECT nombre, empresa_nombre, telefono, correo FROM clientes WHERE id = ?", (user_id,))
            user_data = cursor.fetchone()

            formato = request.args.get('formato', 'ticket')  # 'ticket' (80mm) o 'carta'

            return render_template(
                'ventas/comprobante_pdf.html',
                venta=venta,
                items=items,
                user_data=user_data,
                formato=formato
            )

        except Exception as e:
            app.logger.error(f"Error al cargar comprobante de venta {id}: {e}")
            flash(f"Error cargando comprobante: {str(e)}", "danger")
            return redirect(url_for('ventas_pos'))
        finally:
            conexion.close()


    @app.route('/ventas/<int:id>/anular', methods=['POST'])
    @login_required
    def anular_venta(id):
        user_id = session.get('user_id')
        user_rol = session.get('user_rol')

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            if not _validar_acceso_venta(cursor, id, user_id, user_rol):
                return jsonify({'success': False, 'message': 'No tienes permisos para anular esta venta'}), 403

            cursor.execute("SELECT id, codigo_venta, estado_pago, vendedor_id, creador_id FROM ventas WHERE id = ?", (id,))
            venta = cursor.fetchone()

            if not venta:
                return jsonify({'success': False, 'message': 'Venta no encontrada'}), 404

            # Restricción de seguridad: usuarios standard solo pueden anular sus propias ventas
            if user_rol == 'standard' and venta['vendedor_id'] != user_id:
                return jsonify({'success': False, 'message': 'Solo el Administrador o el vendedor emisor pueden anular esta venta'}), 403

            if venta['estado_pago'] == 'anulado':
                return jsonify({'success': False, 'message': 'La venta ya se encuentra anulada'}), 400

            # Restituir stock físico
            cursor.execute("SELECT producto_id, cantidad FROM venta_productos WHERE venta_id = ?", (id,))
            items = cursor.fetchall()

            for item in items:
                cursor.execute("""
                    UPDATE productos 
                    SET cantidad = cantidad + ?,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (item['cantidad'], item['producto_id']))

            # Marcar venta como anulada
            cursor.execute("UPDATE ventas SET estado_pago = 'anulado' WHERE id = ?", (id,))

            conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="anular_venta",
                detalle={"venta_id": id, "codigo_venta": venta['codigo_venta']}
            )

            return jsonify({
                'success': True, 
                'message': f"Venta {venta['codigo_venta']} anulada con éxito y stock restituido al inventario."
            })

        except Exception as e:
            conexion.rollback()
            app.logger.error(f"Error anulando venta {id}: {e}")
            return jsonify({'success': False, 'message': f'Error al anular venta: {str(e)}'}), 500
        finally:
            conexion.close()
