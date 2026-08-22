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

def register_routes(app):
    @app.route('/')
    def index():
        # Si el usuario ya está autenticado, redirigir a su panel correspondiente sin destruir sesión
        if 'user_id' in session:
            if session.get('user_rol') == 'standard':
                return redirect(url_for('standard_dashboard'))
            return redirect(url_for('dashboard'))

        # Si no está autenticado, mostrar landing page
        return render_template('landing.html')

    @app.route('/acerca-de')
    def acerca_de():
        return render_template('acerca_de.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user_id = session.get('user_id')
        user_rol = session.get('user_rol', 'standard')

        # Redirigir usuarios standard inmediatamente
        if user_rol == 'standard':
            return redirect(url_for('standard_dashboard'))

        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            # ─── VISTA SUPERADMIN (MÉTRICAS SAAS GLOBALES) ───────────────────────────
            if user_rol == 'superadmin':
                cursor.execute("SELECT COUNT(*) FROM clientes WHERE rol = 'admin'")
                row = cursor.fetchone()
                total_admins = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM clientes WHERE rol = 'standard'")
                row = cursor.fetchone()
                total_vendors = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM cotizaciones")
                row = cursor.fetchone()
                total_cotizaciones = row[0] if row else 0
            
                cursor.execute('''
                    SELECT c.id, c.fecha, cli.nombre as cliente, v.nombre as vendedor, c.total, c.estado
                    FROM cotizaciones c
                    JOIN clientes cli ON c.cliente_id = cli.id
                    LEFT JOIN clientes v ON c.creador_id = v.id
                    ORDER BY c.fecha DESC LIMIT 10
                ''')
                cotizaciones = cursor.fetchall()
            
                return render_template('admin/dashboard_superadmin.html',
                    total_admins=total_admins,
                    total_vendors=total_vendors,
                    total_cotizaciones=total_cotizaciones,
                    cotizaciones=cotizaciones
                )

            # ─── VISTA ADMIN (MÉTRICAS Y ACTIVIDADES AISLADAS POR EMPRESA / TENANT) ──
            # 1. Total Clientes creados por el admin
            cursor.execute("SELECT COUNT(*) FROM clientes WHERE creador_id = ? AND rol = 'cliente'", (user_id,))
            row = cursor.fetchone()
            total_usuarios = row[0] if row else 0

            # 2. Total Productos disponibles para el admin
            cursor.execute("SELECT COUNT(*) FROM productos WHERE creador_id = ? OR creador_id IS NULL", (user_id,))
            row = cursor.fetchone()
            total_productos = row[0] if row else 0

            # 3. Total Cotizaciones del negocio (admin + sus vendedores)
            cursor.execute('''
                SELECT COUNT(*) FROM cotizaciones 
                WHERE creador_id = ? OR creador_id IN (SELECT id FROM clientes WHERE creador_id = ?)
            ''', (user_id, user_id))
            row = cursor.fetchone()
            total_cotizaciones = row[0] if row else 0

            # 4. Actividad Reciente del negocio (Top 10)
            cursor.execute('''
                SELECT c.id, c.fecha, COALESCE(cli.nombre, 'Sin asignar') as cliente, COALESCE(c.total, 0) as total, c.estado
                FROM cotizaciones c
                LEFT JOIN clientes cli ON c.cliente_id = cli.id
                WHERE c.creador_id = ? OR c.creador_id IN (SELECT id FROM clientes WHERE creador_id = ?)
                ORDER BY c.fecha DESC
                LIMIT 10
            ''', (user_id, user_id))
            actividades_recientes = cursor.fetchall()

            # 5. Estadísticas de Cotizaciones por Estado del negocio
            estados = ['Aprobada', 'Pendiente', 'Rechazada']
            cotizaciones_estado = {'aprobadas': [], 'pendientes': [], 'rechazadas': []}
            cotizaciones_aprobadas = cotizaciones_pendientes = cotizaciones_rechazadas = 0

            for estado, key in zip(estados, ['aprobadas', 'pendientes', 'rechazadas']):
                if estado == 'Pendiente':
                    cursor.execute('''
                        SELECT c.id, c.fecha, COALESCE(cli.nombre, 'Sin asignar') as cliente, COALESCE(c.total, 0) as total
                        FROM cotizaciones c
                        LEFT JOIN clientes cli ON c.cliente_id = cli.id
                        WHERE (c.creador_id = ? OR c.creador_id IN (SELECT id FROM clientes WHERE creador_id = ?))
                          AND (LOWER(c.estado) = 'pendiente' OR c.estado IS NULL OR c.estado = '')
                        ORDER BY c.fecha DESC
                    ''', (user_id, user_id))
                else:
                    cursor.execute('''
                        SELECT c.id, c.fecha, COALESCE(cli.nombre, 'Sin asignar') as cliente, COALESCE(c.total, 0) as total
                        FROM cotizaciones c
                        LEFT JOIN clientes cli ON c.cliente_id = cli.id
                        WHERE (c.creador_id = ? OR c.creador_id IN (SELECT id FROM clientes WHERE creador_id = ?))
                          AND LOWER(c.estado) = ?
                        ORDER BY c.fecha DESC
                    ''', (user_id, user_id, estado.lower()))
                cotizaciones_estado[key] = cursor.fetchall()
                count = len(cotizaciones_estado[key])
                if key == 'aprobadas':
                    cotizaciones_aprobadas = count
                elif key == 'pendientes':
                    cotizaciones_pendientes = count
                elif key == 'rechazadas':
                    cotizaciones_rechazadas = count

            return render_template('admin/admin_dashboard.html',
                                   nombre=session.get('user_nombre', 'Administrador'),
                                   rol=user_rol,
                                   total_usuarios=total_usuarios,
                                   total_productos=total_productos,
                                   total_cotizaciones=total_cotizaciones,
                                   actividades_recientes=actividades_recientes,
                                   cotizaciones_aprobadas=cotizaciones_aprobadas,
                                   cotizaciones_pendientes=cotizaciones_pendientes,
                                   cotizaciones_rechazadas=cotizaciones_rechazadas,
                                   cotizaciones_estado=cotizaciones_estado,
                                   autenticado=True)
        finally:
            conexion.close()

    @app.route('/standard/dashboard')
    @standard_required
    @login_required
    def standard_dashboard():
        user_id = session.get('user_id')
        conexion = get_db_connection()
        conexion.row_factory = sqlite3.Row
        cursor = conexion.cursor()

        try:
            # 1. Cotizaciones creadas exclusivamente por este vendedor
            cursor.execute('''
                SELECT c.id, c.fecha, c.total, c.estado,
                       co.nombre as cliente_nombre
                FROM cotizaciones c
                LEFT JOIN clientes co ON c.cliente_id = co.id
                WHERE c.creador_id = ?
                ORDER BY c.fecha DESC
            ''', (user_id,))
            cotizaciones = [dict(row) for row in cursor.fetchall()]

            # Métricas calculadas con normalización case-insensitive
            total_cotizaciones = len(cotizaciones)
            total_cotizado = sum(float(c.get('total') or 0) for c in cotizaciones)
            cotizaciones_aprobadas = sum(1 for c in cotizaciones if str(c.get('estado') or '').lower() == 'aprobada')
            cotizaciones_pendientes = sum(1 for c in cotizaciones if str(c.get('estado') or '').lower() in ['pendiente', ''])
            cotizaciones_rechazadas = sum(1 for c in cotizaciones if str(c.get('estado') or '').lower() == 'rechazada')

            # 2. Tareas asignadas al usuario
            cursor.execute('''
                SELECT t.id, t.creador_id, uc.nombre as creador_nombre,
                       t.titulo, t.descripcion, t.prioridad, t.estado,
                       t.fecha_creacion, t.fecha_limite
                FROM equipo_tareas t
                JOIN clientes uc ON t.creador_id = uc.id
                WHERE (t.asignado_a = ? OR t.asignado_a IS NULL) AND t.estado = 'pendiente'
                ORDER BY t.id DESC LIMIT 5
            ''', (user_id,))
            tareas_pendientes = [dict(row) for row in cursor.fetchall()]

            # 3. Anuncios fijados
            cursor.execute('''
                SELECT c.id, u.nombre as usuario_nombre, c.mensaje, c.fecha
                FROM equipo_chat c
                JOIN clientes u ON c.usuario_id = u.id
                WHERE c.es_fijado = TRUE
                ORDER BY c.fecha DESC LIMIT 3
            ''')
            anuncios_fijados = [dict(row) for row in cursor.fetchall()]

            return render_template(
                'standard/standard_dashboard.html',
                nombre=session.get('user_nombre', 'Vendedor'),
                cotizaciones=cotizaciones[:8],
                total_cotizaciones=total_cotizaciones,
                total_cotizado=total_cotizado,
                cotizaciones_aprobadas=cotizaciones_aprobadas,
                cotizaciones_pendientes=cotizaciones_pendientes,
                cotizaciones_rechazadas=cotizaciones_rechazadas,
                tareas_pendientes=tareas_pendientes,
                anuncios_fijados=anuncios_fijados
            )
        except Exception as e:
            app.logger.error(f"Error en standard_dashboard: {str(e)}")
            return render_template(
                'standard/standard_dashboard.html',
                nombre=session.get('user_nombre', 'Vendedor'),
                cotizaciones=[],
                total_cotizaciones=0,
                total_cotizado=0.0,
                cotizaciones_aprobadas=0,
                cotizaciones_pendientes=0,
                cotizaciones_rechazadas=0,
                tareas_pendientes=[],
                anuncios_fijados=[]
            )
        finally:
            conexion.close()

    @app.route('/cotizaciones/standard', endpoint='standard_cotizaciones', methods=['GET'])
    @standard_required
    @login_required
    def standard_cotizaciones():
        # Obtener parámetros de filtro
        estado = request.args.get('estado', '')
        desde = request.args.get('desde', '')
        hasta = request.args.get('hasta', '')

        conexion = get_db_connection()
        cursor = conexion.cursor()

        query = '''
            SELECT 
                c.id, 
                c.fecha, 
                c.total,
                c.estado
            FROM cotizaciones c
            WHERE c.cliente_id = ?
        '''
        params = [session['user_id']]

        # Aplicar filtros
        if estado:
            query += " AND c.estado = ?"
            params.append(estado)

        if desde:
            query += " AND DATE(c.fecha) >= ?"
            params.append(desde)

        if hasta:
            query += " AND DATE(c.fecha) <= ?"
            params.append(hasta)

        query += " ORDER BY c.fecha DESC"

        cursor.execute(query, params)
        cotizaciones = cursor.fetchall()
        conexion.close()

        return render_template('standard/standard_cotizaciones.html',
                               cotizaciones=cotizaciones,
                               filtros={'estado': estado, 'desde': desde, 'hasta': hasta})

    @app.route('/perfil', methods=['GET', 'POST'])
    @login_required
    def perfil():
        try:
            conexion = get_db_connection()
            conexion.row_factory = sqlite3.Row  # Esto hace que los resultados sean diccionarios
            cursor = conexion.cursor()

            if request.method == 'POST':
                nombre = request.form.get('nombre')
                telefono = request.form.get('telefono')
                correo = request.form.get('correo')

                cursor.execute('''
                    UPDATE clientes 
                    SET nombre = ?, telefono = ?, correo = ?
                    WHERE id = ?
                ''', (nombre, telefono, correo, session['user_id']))

                try:
                    cursor.execute('''
                        UPDATE configuracion_pdf
                        SET responsable_nombre = ?, responsable_telefono = ?, responsable_email = ?
                        WHERE usuario_id = ?
                    ''', (nombre, telefono, correo, session['user_id']))
                except Exception:
                    pass

                conexion.commit()

                # Actualizar la sesión
                session['user_nombre'] = nombre
                session['user_email'] = correo
                session['user_telefono'] = telefono
                flash('Perfil actualizado correctamente', 'success')
                return redirect(url_for('perfil'))

            # Obtener datos actuales del usuario
            cursor.execute('''
                SELECT nombre, correo, telefono 
                FROM clientes 
                WHERE id = ?
            ''', (session['user_id'],))
            usuario = cursor.fetchone()

            # Crear diccionario de filtros para evitar errores en la plantilla
            filtros = {
                'cliente': '',
                'codigo_cliente': '',
                'desde': '',
                'hasta': '',
                'estado': ''
            }
        
            return render_template('perfil.html', usuario=usuario, filtros=filtros)

        except Exception as e:
            app.logger.error(f"Error en perfil: {str(e)}")
            flash('Ocurrió un error al procesar tu solicitud', 'danger')
            return redirect(url_for('dashboard'))
        finally:
            if 'conexion' in locals():
                conexion.close()

