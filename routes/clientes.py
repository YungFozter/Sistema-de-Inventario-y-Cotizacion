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
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
import logging
from utils.decorators import login_required, superadmin_required, admin_required, standard_required
from utils.helpers import format_date, aplicar_fondos_por_pagina, generar_pdf_margenes_dinamicos

import re

def generar_codigo_cliente_unico(cursor, creador_id=None):
    """
    Genera un código secuencial rellenando huecos de clientes eliminados.
    Lógica reescrita para garantizar que detecte correctamente números pasados
    incluso si tienen espacios o formatos extraños (ej: 'CLI - 001').
    """
    usados = set()
    try:
        # Traer todos los códigos del admin (no solo los que empiezan por CLI para evitar problemas de LIKE)
        if creador_id:
            cursor.execute("SELECT codigo_cliente FROM clientes WHERE creador_id = ? AND rol = 'cliente' AND codigo_cliente IS NOT NULL", (creador_id,))
        else:
            cursor.execute("SELECT codigo_cliente FROM clientes WHERE rol = 'cliente' AND codigo_cliente IS NOT NULL")
            
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                try:
                    cod = None
                    if isinstance(row, dict) and 'codigo_cliente' in row:
                        cod = row['codigo_cliente']
                    elif hasattr(row, 'keys') and 'codigo_cliente' in dir(row): # fallback
                        try:
                            cod = row['codigo_cliente']
                        except:
                            cod = row[0] if len(row) > 0 else None
                    elif isinstance(row, (list, tuple)) and len(row) > 0:
                        cod = row[0]
                    else:
                        # Intento ciego
                        cod = str(row[0]) if row else None

                    if cod and isinstance(cod, str):
                        cod = cod.strip().upper()
                        # Buscar cualquier número asociado a CLI
                        match = re.search(r'CLI\D*(\d+)', cod)
                        if match:
                            usados.add(int(match.group(1)))
                except Exception as parse_err:
                    continue
    except Exception as e:
        print(f"[ERROR] Error al generar codigo cliente unico: {e}")

    num = 1
    while num in usados:
        num += 1

    return f"CLI-{num:04d}"

def register_routes(app):
    @app.route('/clientes', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def clientes():
        if request.method == 'POST':
            try:
                # Obtener datos del formulario
                razon_social = request.form.get('razon_social', '').strip()
                nit = request.form.get('nit', '').strip()
                if not nit:
                    nit = 'S/A'
                codigo_cliente = request.form.get('codigo_cliente', '').strip()
                telefono = request.form.get('telefono', '').strip()
                if not telefono:
                    telefono = 'S/A'
                referencia = request.form.get('referencia', '').strip()

                # Validaciones
                if not razon_social:
                    flash('El nombre/razón social es obligatorio', 'danger')
                    return redirect(url_for('clientes'))

                conexion = get_db_connection()
                cursor = conexion.cursor()

                # Generar código de cliente automático aislado por empresa/admin
                if not codigo_cliente:
                    codigo_cliente = generar_codigo_cliente_unico(cursor, creador_id=session['user_id'])
                else:
                    # Validar que el código de cliente no se repita en esta misma empresa/admin
                    cursor.execute("SELECT id FROM clientes WHERE creador_id = ? AND codigo_cliente = ? AND rol = 'cliente'", (session['user_id'], codigo_cliente))
                    if cursor.fetchone():
                        flash(f'El código de cliente "{codigo_cliente}" ya está registrado en tu empresa. Usa uno diferente.', 'danger')
                        conexion.close()
                        return redirect(url_for('clientes'))

                cursor.execute('''
                    INSERT INTO clientes (
                        nombre, nit, codigo_cliente, telefono, referencia, 
                        creador_id, rol
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    razon_social, nit, codigo_cliente, telefono,
                    referencia, session['user_id'], 'cliente'
                ))

                nuevo_id = cursor.lastrowid
                conexion.commit()

                # Registrar en logs de auditoría
                registrar_log(
                    usuario_id=session['user_id'],
                    accion="crear_cliente",
                    detalle={
                        "cliente_id": nuevo_id,
                        "nombre": razon_social,
                        "codigo_cliente": codigo_cliente,
                        "nit": nit
                    }
                )

                flash('Cliente registrado exitosamente', 'success')

            except Exception as e:
                flash(f'Error al registrar cliente: {str(e)}', 'danger')
            finally:
                if 'conexion' in locals():
                    conexion.close()

            return redirect(url_for('clientes'))

        # Método GET - Mostrar lista de clientes con paginación
        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()

            # Parámetros de paginación
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 15, type=int)
            if per_page not in [15, 30, 50]:
                per_page = 15

            offset = (page - 1) * per_page
            busqueda = request.args.get('buscar', '').strip()

            # Consulta base diferente para superadmin - Seleccionar columnas explícitas para asegurar posiciones en _clientes_lista.html
            if session.get('user_rol') == 'superadmin':
                count_query = "SELECT COUNT(*) FROM clientes WHERE rol = 'cliente'"
                query = "SELECT id, nombre, nit, codigo_cliente, telefono, referencia, creador_id FROM clientes WHERE rol = 'cliente'"
                params = []
            else:
                count_query = "SELECT COUNT(*) FROM clientes WHERE creador_id = ? AND rol = 'cliente'"
                query = "SELECT id, nombre, nit, codigo_cliente, telefono, referencia, creador_id FROM clientes WHERE creador_id = ? AND rol = 'cliente'"
                params = [session['user_id']]

            if busqueda:
                search_condition = '''
                    AND (nombre LIKE ? OR 
                         nit LIKE ? OR 
                         codigo_cliente LIKE ? OR 
                         telefono LIKE ? OR 
                         referencia LIKE ?)
                '''
                count_query += search_condition
                query += search_condition
                search_param = f"%{busqueda}%"
                params.extend([search_param] * 5)

            # Obtener el total de registros para la paginación
            cursor.execute(count_query, params)
            res_count = cursor.fetchone()
            total_clientes = res_count[0] if (res_count and len(res_count) > 0) else 0

            # Calcular el número total de páginas
            total_pages = max(1, (total_clientes + per_page - 1) // per_page)
            if page > total_pages:
                page = total_pages
                offset = (page - 1) * per_page
            if page < 1:
                page = 1
                offset = 0

            # Obtener los clientes para la página actual
            query += " ORDER BY nombre LIMIT ? OFFSET ?"
            cursor.execute(query, params + [per_page, offset])
            clientes = cursor.fetchall()

        except Exception as e:
            flash(f'Error al cargar clientes: {str(e)}', 'danger')
            clientes = []
            total_pages = 1
            page = 1
            total_clientes = 0
        finally:
            if 'conexion' in locals():
                conexion.close()

        # Crear diccionario de filtros para evitar errores en la plantilla
        filtros = {
            'cliente': '',
            'codigo_cliente': '',
            'desde': '',
            'hasta': '',
            'estado': ''
        }

        # Datos de paginación
        pagination = {
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'total_items': total_clientes
        }

        if request.args.get('ajax') == '1' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('clientes/_clientes_lista.html', clientes=clientes, filtros=filtros, pagination=pagination)

        return render_template('clientes/clientes.html', clientes=clientes, filtros=filtros, pagination=pagination)

    @app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def editar_cliente(id):
        conexion = get_db_connection()
        cursor = conexion.cursor()

        # Verificar que el cliente pertenece al admin actual o es superadmin, y que sea realmente un cliente
        cursor.execute("SELECT creador_id FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
        cliente = cursor.fetchone()

        if not cliente or (cliente[0] != session['user_id'] and session.get('user_rol') != 'superadmin'):
            flash('No tienes permisos para editar este cliente, o no existe.', 'danger')
            return redirect(url_for('clientes'))


        if request.method == 'POST':
            # Obtener datos del formulario
            nombre = request.form.get('nombre', '').strip()
            nit = request.form.get('nit', '').strip()
            if not nit:
                nit = 'S/A'
            codigo_cliente = request.form.get('codigo_cliente', '').strip()
            telefono = request.form.get('telefono', '').strip()
            if not telefono:
                telefono = 'S/A'
            referencia = request.form.get('referencia', '').strip()

            creador_target = cliente[0] if session.get('user_rol') == 'superadmin' else session['user_id']
            if not codigo_cliente:
                codigo_cliente = generar_codigo_cliente_unico(cursor, creador_id=creador_target)
            else:
                cursor.execute("SELECT id FROM clientes WHERE creador_id = ? AND codigo_cliente = ? AND id != ? AND rol = 'cliente'", (creador_target, codigo_cliente, id))
                if cursor.fetchone():
                    flash(f'El código de cliente "{codigo_cliente}" ya pertenece a otro cliente en tu empresa.', 'danger')
                    conexion.close()
                    return redirect(url_for('editar_cliente', id=id))

            # Actualizar en la base de datos
            cursor.execute('''
                UPDATE clientes SET 
                    nombre = ?,
                    nit = ?,
                    codigo_cliente = ?,
                    telefono = ?,
                    referencia = ?
                WHERE id = ?
            ''', (nombre, nit, codigo_cliente, telefono, referencia, id))

            conexion.commit()
            conexion.close()
            flash('Cliente actualizado correctamente', 'success')
            return redirect('/clientes')

        # GET - Mostrar formulario de edición
        cursor.execute("SELECT * FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
        cliente = cursor.fetchone()
        conexion.close()

        # Crear diccionario de filtros para evitar errores en la plantilla
        filtros = {
            'cliente': '',
            'codigo_cliente': '',
            'desde': '',
            'hasta': '',
            'estado': ''
        }
    
        return render_template('clientes/editar_cliente.html', cliente=cliente, filtros=filtros)

    @app.route('/clientes/eliminar/<int:id>')
    @login_required
    @admin_required
    def eliminar_cliente(id):
        conexion = get_db_connection()
        cursor = conexion.cursor()

        # Verificar que el cliente pertenece al admin actual o es superadmin, y que sea realmente un cliente
        cursor.execute("SELECT creador_id, nombre FROM clientes WHERE id = ? AND rol = 'cliente'", (id,))
        cliente = cursor.fetchone()

        if not cliente or (cliente[0] != session['user_id'] and session.get('user_rol') != 'superadmin'):
            flash('No tienes permisos para eliminar este cliente, o no existe.', 'danger')
            return redirect(url_for('clientes'))

        # Registrar antes de eliminar
        registrar_log(
            usuario_id=session['user_id'],
            accion="eliminar_cliente",
            detalle={
                "cliente_id": id,
                "nombre_cliente": cliente[1] if cliente else "Desconocido"
            }
        )

        # Eliminar cotizaciones y sus productos asociados al cliente
        cursor.execute('''
            DELETE FROM cotizacion_productos WHERE cotizacion_id IN (
                SELECT id FROM cotizaciones WHERE cliente_id = ?
            )
        ''', (id,))
        cursor.execute("DELETE FROM cotizaciones WHERE cliente_id = ?", (id,))

        # Eliminar cliente
        cursor.execute('DELETE FROM clientes WHERE id=?', (id,))
        conexion.commit()
        conexion.close()

        flash('Cliente eliminado correctamente', 'success')
        return redirect('/clientes')

    @app.route('/api/validar-nit')
    @login_required
    def api_validar_nit():
        nit = request.args.get('nit', '').strip()
        if not nit:
            return jsonify({
                'valido': True,
                'vacio': True,
                'mensaje': 'Campo en blanco: se guardará automáticamente como S/A (Sin Asignar).'
            })

        conexion = get_db_connection()
        cursor = conexion.cursor()

        owner_id = session.get('creador_id') or session.get('user_id')
        if session.get('user_rol') == 'superadmin':
            cursor.execute("SELECT id, nombre FROM clientes WHERE nit = ? AND nit NOT IN ('S/A', 'S/N') AND rol = 'cliente'", (nit,))
        else:
            cursor.execute('''
                SELECT id, nombre FROM clientes 
                WHERE nit = ? AND nit NOT IN ('S/A', 'S/N') AND rol = 'cliente' 
                  AND (creador_id = ? OR creador_id = ?)
            ''', (nit, owner_id, session.get('user_id')))

        existente = cursor.fetchone()
        conexion.close()

        if existente:
            return jsonify({
                'valido': False,
                'mensaje': f'El NIT/CI "{nit}" ya está registrado en tu empresa para el cliente: "{existente[1]}".'
            })

        return jsonify({
            'valido': True,
            'vacio': False,
            'mensaje': f'El NIT/CI "{nit}" está disponible para registrar.'
        })

