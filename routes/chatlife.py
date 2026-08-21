import json
import sqlite3
import requests
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from db_wrapper import get_db_connection
from utils.decorators import login_required, admin_required
from models import registrar_log

def procesar_respuesta_ia(user_id, empresa, mensaje_cliente, system_prompt=None, openai_api_key=None):
    """
    Procesa la pregunta del cliente consultando el inventario de productos en tiempo real.
    Si se provee openai_api_key, utiliza OpenAI GPT API. De lo contrario, utiliza un motor inteligente interno.
    """
    productos_lista = []
    try:
        with get_db_connection() as conexion:
            conexion.row_factory = sqlite3.Row
            cursor = conexion.cursor()
            cursor.execute('''
                SELECT p.codigo, p.descripcion, p.marca, p.precio_unitario, p.cantidad, p.um, c.nombre as categoria_nombre, p.categoria
                FROM productos p
                LEFT JOIN categorias c ON p.categoria_id = c.id
                WHERE (p.empresa = ? OR p.creador_id = ?) AND (p.activo IS TRUE OR p.activo = 1)
                LIMIT 50
            ''', (empresa, user_id))
            productos_lista = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        print(f"[WARN ChatLive] Error cargando catálogo: {e}")

    # Si hay OpenAI API Key configurada, llamamos a la API de OpenAI
    if openai_api_key and openai_api_key.strip():
        catalog_context = []
        for r in productos_lista:
            cat = r.get('categoria_nombre') or r.get('categoria') or 'General'
            catalog_context.append(
                f"- Código: {r['codigo']} | {r['descripcion']} ({r['marca'] or 'Genérico'}) | Categoría: {cat} | Precio: {r['precio_unitario']} Bs | Stock: {r['cantidad']} {r['um'] or 'UN'}"
            )
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
            print(f"[WARN ChatLive] Error llamando a OpenAI API: {e_ai}")

    # Fallback: Motor Inteligente Basado en Inventario Real (Sin API Key)
    msg_lower = mensaje_cliente.lower().strip()
    
    stop_words = {'que', 'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'a', 'ante', 'con', 'para', 'por', 'sin', 'sobre', 'y', 'o', 'tienen', 'tiene', 'precio', 'precios', 'cuanto', 'cuantes', 'cuanto', 'cuantos', 'cual', 'cuales', 'son', 'misma', 'mi', 'su', 'sus', 'es', 'son', 'esta', 'estan', 'disponible', 'disponibilidad', 'stock', 'cotizacion', 'cotizar', 'necesito', 'quiero', 'favor', 'hola', 'buenas', 'buenos', 'dias', 'tardes', 'noches', 'vendidos', 'mas', 'menos'}

    words = [w.strip('?,.!;:') for w in msg_lower.split() if w.strip('?,.!;:') not in stop_words and len(w.strip('?,.!;:')) > 2]

    coincidencias = []
    if words:
        for p in productos_lista:
            p_desc = (p['descripcion'] or '').lower()
            p_cod = (p['codigo'] or '').lower()
            p_marca = (p['marca'] or '').lower()
            p_cat = ((p.get('categoria_nombre') or p.get('categoria')) or '').lower()
            if any(w in p_desc or w in p_cod or w in p_marca or w in p_cat for w in words):
                coincidencias.append(p)

    # Caso A: Se encontraron coincidencias específicas de productos
    if coincidencias:
        res_items = []
        for p in coincidencias[:6]:
            res_items.append(f"• *{p['descripcion']}* ({p['marca'] or 'Marca Estándar'})\n  👉 Precio: *{p['precio_unitario']} Bs* | Stock: *{p['cantidad']} {p['um'] or 'UN'}* (Código: `{p['codigo']}`)")
        
        return f"¡Hola! 👋 Gracias por consultar con *{empresa}*.\n\nEncontramos estos productos en nuestro catálogo:\n\n" + "\n\n".join(res_items) + "\n\n¿Deseas incluir alguno de estos ítems en una cotización formal?"

    # Caso B: Consultas generales sobre catálogo, precios, stock o cotizaciones
    if productos_lista:
        res_items = []
        for p in productos_lista[:6]:
            res_items.append(f"• *{p['descripcion']}* — *{p['precio_unitario']} Bs* (Stock: {p['cantidad']} {p['um'] or 'UN'})")
        
        if "cotiz" in msg_lower:
            return f"¡Hola! 👋 Con gusto te preparamos una cotización formal en *{empresa}*.\n\nNuestros productos disponibles son:\n\n" + "\n".join(res_items) + "\n\n¿Dime qué productos y qué cantidad necesitas para generarte la cotización al instante?"
        elif "vendido" in msg_lower or "mas" in msg_lower:
            return f"¡Hola! 👋 En *{empresa}*, los productos más destacados de nuestro catálogo son:\n\n" + "\n".join(res_items) + "\n\n¿Te gustaría cotizar alguno de ellos?"
        else:
            return f"¡Hola! 👋 Bienvenido a *{empresa}*.\n\nActualmente contamos con los siguientes productos en inventario:\n\n" + "\n".join(res_items) + "\n\n¿Qué producto o cantidad te gustaría consultar?"

    # Caso C: No hay productos registrados aún
    return f"¡Hola! 👋 Bienvenido a *{empresa}*. Actualmente estamos actualizando nuestro inventario. Por favor déjanos el detalle de lo que necesitas y un asesor te responderá a la brevedad."

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
                cursor.execute("SELECT * FROM chatlife_mensajes WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
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
            bot_activo = 1 if request.form.get('bot_activo') == '1' else 0
            auto_crear_clientes = 1 if request.form.get('auto_crear_clientes') == '1' else 0

            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                cursor.execute('''
                    UPDATE chatlife_config
                    SET phone_number_id=?, waba_id=?, verify_token=?, access_token=?, openai_api_key=?, system_prompt=?, bot_activo=?, auto_crear_clientes=?, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE user_id=?
                ''', (phone_number_id, waba_id, verify_token, access_token, openai_api_key, system_prompt, bot_activo, auto_crear_clientes, user_id))
                conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="guardar_config_chatlife",
                detalle={
                    "phone_number_id": phone_number_id,
                    "waba_id": waba_id,
                    "bot_activo": bool(bot_activo),
                    "auto_crear_clientes": bool(auto_crear_clientes),
                    "tiene_openai_key": bool(openai_api_key)
                }
            )

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
                    VALUES (?, ?, ?, ?, ?, 1)
                ''', (user_id, '+591 (Simulador)', 'Cliente Prueba', mensaje_cliente, respuesta_ia))
                conexion.commit()

                return jsonify({
                    'success': True,
                    'respuesta': respuesta_ia
                })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/api/chatlife/limpiar-historial', methods=['POST'])
    @login_required
    @admin_required
    def limpiar_historial_chatlife():
        """Elimina mensajes de simulación o historial completo del tenant actual (Anti-IDOR)."""
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or request.form or {}
        tipo = data.get('tipo', 'simulacion')

        try:
            with get_db_connection() as conexion:
                cursor = conexion.cursor()
                if tipo == 'simulacion':
                    cursor.execute("DELETE FROM chatlife_mensajes WHERE user_id = ? AND (es_simulacion IS TRUE OR es_simulacion = 1)", (user_id,))
                else:
                    cursor.execute("DELETE FROM chatlife_mensajes WHERE user_id = ?", (user_id,))
                conexion.commit()

            registrar_log(
                usuario_id=user_id,
                accion="limpiar_historial_chatlife",
                detalle={"tipo": tipo}
            )

            return jsonify({'success': True, 'message': 'Historial limpiado exitosamente.'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

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
                        cursor.execute("SELECT user_id, verify_token FROM chatlife_config WHERE verify_token = ?", (token,))
                        match = cursor.fetchone()
                        if match:
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

                        if not phone_number_id:
                            continue

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

                                    # Aislamiento Multi-Tenant Estricto por Phone Number ID
                                    cursor.execute("SELECT * FROM chatlife_config WHERE phone_number_id = ? AND (bot_activo IS TRUE OR bot_activo = 1) LIMIT 1", (phone_number_id,))
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
                                            VALUES (?, ?, ?, ?, ?, 0)
                                        ''', (user_id, from_phone, nombre_cliente, text_body, respuesta_bot))
                                        conexion.commit()

            except Exception as e_main:
                print(f"[WARN ChatLife] Error en webhook handler: {e_main}")

            return jsonify({'status': 'success'}), 200
