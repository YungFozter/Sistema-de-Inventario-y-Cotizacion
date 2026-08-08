import json
import sqlite3
import requests
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from models import get_db_connection

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión para acceder.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_rol') not in ['admin', 'superadmin']:
            flash('Acceso restringido a administradores.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def procesar_respuesta_ia(user_id, empresa, mensaje_cliente, system_prompt=None, openai_api_key=None):
    """
    Procesa la pregunta del cliente consultando el inventario de productos en tiempo real.
    Si se provee openai_api_key, utiliza OpenAI GPT API. De lo contrario, utiliza un motor inteligente interno.
    """
    catalog_context = []
    try:
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute('''
                SELECT p.codigo, p.descripcion, p.marca, p.precio_unitario, p.cantidad, p.um, c.nombre as categoria_nombre, p.categoria
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                WHERE p.empresa = ? OR p.creador_id = ?
                LIMIT 50
            ''', (empresa, user_id))
            rows = cursor.fetchall()
            for r in rows:
                cat = r['categoria_nombre'] or r['categoria'] or 'General'
                catalog_context.append(
                    f"- Código: {r['codigo']} | {r['descripcion']} ({r['marca'] or 'Genérico'}) | Categoría: {cat} | Precio: {r['precio_unitario']} Bs | Stock Disponible: {r['cantidad']} {r['um'] or 'UN'}"
                )
    except Exception as e:
        print(f"[WARN ChatLife] Error cargando catálogo: {e}")

    cat_text = "\n".join(catalog_context) if catalog_context else "No hay productos en inventario actualmente."

    prompt_base = f"""Eres 'ChatLive IA', el asistente virtual experto en ventas y atención al cliente de la empresa '{empresa}'.
Tu objetivo es responder de forma amable, ejecutiva y persuasiva, brindar precios y stock del inventario y cerrar ventas o agendar cotizaciones.

CATÁLOGO DE PRODUCTOS EN TIEMPO REAL:
{cat_text}

INSTRUCCIONES ADICIONALES:
{system_prompt if system_prompt else 'Brinda respuestas claras y concisas con emojis profesionales.'}

MENSAJE DEL CLIENTE:
"{mensaje_cliente}"
"""

    if openai_api_key and openai_api_key.strip():
        try:
            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_api_key.strip()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": f"Eres el asistente de ventas por WhatsApp de {empresa}."},
                        {"role": "user", "content": prompt_base}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 400
                },
                timeout=12
            )
            if res.status_code == 200:
                data = res.json()
                return data['choices'][0]['message']['content'].strip()
        except Exception as e_ai:
            print(f"[WARN ChatLife] Error llamando a OpenAI API: {e_ai}")

    # Fallback: Motor de Respuestas Inteligente Integrado
    msg_lower = mensaje_cliente.lower()
    coincidencias = []
    
    try:
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute('''
                SELECT descripcion, precio_unitario, cantidad, um, marca 
                FROM productos 
                WHERE (empresa = ? OR creador_id = ?) 
                AND (LOWER(descripcion) LIKE ? OR LOWER(codigo) LIKE ? OR LOWER(marca) LIKE ?)
                LIMIT 5
            ''', (empresa, user_id, f'%{msg_lower}%', f'%{msg_lower}%', f'%{msg_lower}%'))
            coincidencias = cursor.fetchall()
    except Exception:
        pass

    if coincidencias:
        res_items = []
        for item in coincidencias:
            res_items.append(f"• *{item['descripcion']}* ({item['marca'] or 'Marca Estándar'}): *{item['precio_unitario']} Bs* (Stock: {item['cantidad']} {item['um'] or 'UN'})")
        return f"¡Hola! 👋 Gracias por comunicarte con *{empresa}*.\n\nEncontramos los siguientes ítems disponibles en nuestro catálogo:\n\n" + "\n".join(res_items) + "\n\n¿Te gustaría que te preparemos una cotización formal o deseas más información?"
    elif "precio" in msg_lower or "cotiz" in msg_lower or "hola" in msg_lower or "stock" in msg_lower:
        return f"¡Hola! 👋 Bienvenido a *{empresa}*. Contamos con un catálogo completo de insumos y equipos. ¿Qué producto estás buscando hoy para verificarte precio y disponibilidad en tiempo real?"
    else:
        return f"¡Gracias por escribir a *{empresa}*! 🤖 En breve un asesor comercial revisará tu solicitud. Mientras tanto, dime el producto o código de tu interés para enviarte precios y stock."

def register_routes(app):

    @app.route('/chatlife')
    @login_required
    @admin_required
    def chatlife():
        user_id = session.get('user_id')
        config = None
        mensajes = []

        try:
            with get_db_connection() as conexion:
                conexion.row_factory = sqlite3.Row
                cursor = conexion.cursor()

                cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (user_id,))
                u = cursor.fetchone()
                empresa_usuario = u[0] if u and u[0] else (u[1] if u and u[1] else 'General')

                # Cargar o crear configuración
                cursor.execute("SELECT * FROM chatlife_config WHERE user_id = ?", (user_id,))
                row_cfg = cursor.fetchone()
                if row_cfg:
                    config = dict(row_cfg)
                else:
                    default_verify = f"chatlife_token_{user_id}"
                    cursor.execute('''
                        INSERT INTO chatlife_config (user_id, empresa, verify_token, system_prompt)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, empresa_usuario, default_verify, 'Responde con amabilidad, comparte precios de productos y ofrece generar cotizaciones.'))
                    conexion.commit()
                    cursor.execute("SELECT * FROM chatlife_config WHERE user_id = ?", (user_id,))
                    config = dict(cursor.fetchone())

                # Cargar historial de mensajes recientes
                cursor.execute("SELECT * FROM chatlife_mensajes WHERE user_id = ? ORDER BY id DESC LIMIT 30", (user_id,))
                mensajes = [dict(m) for m in cursor.fetchall()]

        except Exception as e:
            flash(f'Error al cargar ChatLife: {str(e)}', 'danger')

        webhook_url = request.host_url.rstrip('/') + "/api/chatlife/webhook"

        return render_template(
            'chatlife/chatlife.html',
            config=config,
            mensajes=mensajes,
            webhook_url=webhook_url
        )

    @app.route('/api/chatlife/guardar-config', methods=['POST'])
    @login_required
    @admin_required
    def guardar_config_chatlife():
        user_id = session.get('user_id')
        try:
            phone_number_id = request.form.get('phone_number_id', '').strip()
            waba_id = request.form.get('waba_id', '').strip()
            verify_token = request.form.get('verify_token', '').strip() or f"chatlife_token_{user_id}"
            access_token = request.form.get('access_token', '').strip()
            openai_api_key = request.form.get('openai_api_key', '').strip()
            system_prompt = request.form.get('system_prompt', '').strip()
            bot_activo = True if request.form.get('bot_activo') == '1' else False
            auto_crear_clientes = True if request.form.get('auto_crear_clientes') == '1' else False

            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                cursor.execute('''
                    UPDATE chatlife_config
                    SET phone_number_id=?, waba_id=?, verify_token=?, access_token=?, openai_api_key=?, system_prompt=?, bot_activo=?, auto_crear_clientes=?, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE user_id=?
                ''', (phone_number_id, waba_id, verify_token, access_token, openai_api_key, system_prompt, bot_activo, auto_crear_clientes, user_id))
                conexion.commit()

            flash('¡Configuración de ChatLife WhatsApp IA guardada correctamente!', 'success')
        except Exception as e:
            flash(f'Error al guardar configuración: {str(e)}', 'danger')

        return redirect(url_for('chatlife'))

    @app.route('/api/chatlife/simular', methods=['POST'])
    @login_required
    @admin_required
    def simular_chatlife():
        user_id = session.get('user_id')
        data = request.get_json() or {}
        mensaje_cliente = data.get('mensaje', '').strip()

        if not mensaje_cliente:
            return jsonify({'success': False, 'error': 'El mensaje no puede estar vacío.'})

        try:
            with get_db_connection() as conexion:
                conexion.row_factory = sqlite3.Row
                cursor = conexion.cursor()

                cursor.execute("SELECT empresa_nombre, nombre FROM clientes WHERE id = ?", (user_id,))
                u = cursor.fetchone()
                empresa_usuario = u[0] if u and u[0] else (u[1] if u and u[1] else 'General')

                cursor.execute("SELECT * FROM chatlife_config WHERE user_id = ?", (user_id,))
                cfg = cursor.fetchone()
                sys_prompt = cfg['system_prompt'] if cfg and cfg['system_prompt'] else None
                api_key = cfg['openai_api_key'] if cfg and cfg['openai_api_key'] else None

                respuesta_ia = procesar_respuesta_ia(user_id, empresa_usuario, mensaje_cliente, sys_prompt, api_key)

                # Registrar mensaje simulado en el historial
                cursor.execute('''
                    INSERT INTO chatlife_mensajes (user_id, telefono_remitente, nombre_remitente, mensaje_cliente, respuesta_bot, es_simulacion)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, '+591 (Simulador)', 'Cliente Prueba', mensaje_cliente, respuesta_ia, True))
                conexion.commit()

                return jsonify({
                    'success': True,
                    'respuesta': respuesta_ia
                })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/api/chatlife/webhook', methods=['GET', 'POST'])
    def webhook_chatlife():
        # GET: Validación de Meta Webhook (Challenge verification)
        if request.method == 'GET':
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            if mode and token:
                try:
                    with get_db_connection() as conexion:
                        cursor = conexion.cursor()
                        cursor.execute("SELECT verify_token FROM chatlife_config WHERE verify_token = ?", (token,))
                        match = cursor.fetchone()
                        if match or token.startswith('chatlife_token'):
                            return challenge, 200
                except Exception:
                    pass
            return 'Verification token mismatch', 403

        # POST: Procesamiento de Mensajes Entrantes de WhatsApp Meta API
        if request.method == 'POST':
            payload = request.get_json() or {}
            try:
                entries = payload.get('entry', [])
                for entry in entries:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})
                        metadata = value.get('metadata', {})
                        phone_number_id = metadata.get('phone_number_id')

                        messages = value.get('messages', [])
                        contacts = value.get('contacts', [])
                        nombre_cliente = contacts[0].get('profile', {}).get('name', 'Cliente WhatsApp') if contacts else 'Cliente WhatsApp'

                        for msg in messages:
                            if msg.get('type') == 'text':
                                from_phone = msg.get('from')
                                text_body = msg.get('text', {}).get('body', '')

                                with get_db_connection() as conexion:
                                    conexion.row_factory = sqlite3.Row
                                    cursor = conexion.cursor()

                                    cursor.execute("SELECT * FROM chatlife_config WHERE phone_number_id = ? OR bot_activo = 1 LIMIT 1", (phone_number_id,))
                                    cfg = cursor.fetchone()

                                    if cfg and cfg['bot_activo']:
                                        user_id = cfg['user_id']
                                        empresa = cfg['empresa']
                                        access_token = cfg['access_token']
                                        sys_prompt = cfg['system_prompt']
                                        api_key = cfg['openai_api_key']

                                        respuesta_bot = procesar_respuesta_ia(user_id, empresa, text_body, sys_prompt, api_key)

                                        # Enviar respuesta vía Meta WhatsApp Graph API si hay access_token
                                        if access_token and phone_number_id:
                                            try:
                                                requests.post(
                                                    f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                                                    headers={
                                                        "Authorization": f"Bearer {access_token}",
                                                        "Content-Type": "application/json"
                                                    },
                                                    json={
                                                        "messaging_product": "whatsapp",
                                                        "to": from_phone,
                                                        "type": "text",
                                                        "text": {"body": respuesta_bot}
                                                    },
                                                    timeout=10
                                                )
                                            except Exception as e_send:
                                                print(f"[WARN ChatLife] Error enviando mensaje por Meta API: {e_send}")

                                        # Auto-crear cliente si está habilitado
                                        if cfg['auto_crear_clientes']:
                                            try:
                                                cursor.execute("SELECT COUNT(*) FROM clientes WHERE telefono = ? AND (creador_id = ? OR empresa_nombre = ?)", (from_phone, user_id, empresa))
                                                if cursor.fetchone()[0] == 0:
                                                    cursor.execute('''
                                                        INSERT INTO clientes (empresa_nombre, nombre, contacto_principal, telefono, creador_id)
                                                        VALUES (?, ?, ?, ?, ?)
                                                    ''', (empresa, f"WhatsApp - {nombre_cliente}", nombre_cliente, from_phone, user_id))
                                            except Exception as e_c:
                                                print(f"[WARN ChatLife] Error auto-creando cliente: {e_c}")

                                        # Registrar en el historial de mensajes
                                        cursor.execute('''
                                            INSERT INTO chatlife_mensajes (user_id, telefono_remitente, nombre_remitente, mensaje_cliente, respuesta_bot, es_simulacion)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                        ''', (user_id, from_phone, nombre_cliente, text_body, respuesta_bot, False))
                                        conexion.commit()

            except Exception as e_main:
                print(f"[WARN ChatLife] Error en webhook handler: {e_main}")

            return jsonify({'status': 'success'}), 200
