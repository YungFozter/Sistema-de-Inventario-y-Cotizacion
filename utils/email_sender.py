"""
utils/email_sender.py
─────────────────────
Utilidad de envío de correos para COTIZAPro.
Soporta SMTP genérico (Gmail, Outlook, etc.) vía TLS.

Variables de entorno requeridas en .env:
    MAIL_SERVER     → smtp.gmail.com
    MAIL_PORT       → 587
    MAIL_USERNAME   → tu-correo@gmail.com
    MAIL_PASSWORD   → App Password de Google (sin espacios)
    MAIL_FROM_NAME  → COTIZAPro  (opcional)

Modo Desarrollo:
    Si MAIL_USERNAME no está configurado, el código se imprime en
    la consola del servidor en lugar de enviarse por email.
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ─── Leer configuración desde entorno ────────────────────────────────────────
MAIL_SERVER   = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
MAIL_PORT     = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM_NAME = os.environ.get('MAIL_FROM_NAME', 'COTIZAPro')


# ─── Template HTML del email ──────────────────────────────────────────────────
def _build_email_html(nombre: str, codigo: str) -> str:
    """Genera el cuerpo HTML del correo de verificación enriquecido."""
    digitos_html = ''.join(
        f'<span style="display:inline-block; width:46px; height:56px; line-height:56px;'
        f' text-align:center; font-size:1.75rem; font-weight:900; color:#1C1917;'
        f' background:#F4F3EE; border:2px solid #e5e2da; border-radius:12px;'
        f' margin:0 3px; letter-spacing:0; font-family:monospace;">{d}</span>'
        for d in codigo
    )

    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Código de verificación – COTIZAPro</title>
</head>
<body style="margin:0; padding:0; background:#F4F3EE; font-family:'Segoe UI',Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F3EE; padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="background:#FFFFFF; border-radius:24px; overflow:hidden;
                      box-shadow:0 8px 32px rgba(0,0,0,0.08); max-width:100%;">

          <!-- Header naranja -->
          <tr>
            <td style="background:linear-gradient(135deg,#FF6B35,#e85d24);
                       padding:36px 40px 28px; text-align:center;">
              <!-- Icono de correo perfectamente centrado (compatible con Gmail/Outlook) -->
              <table align="center" border="0" cellpadding="0" cellspacing="0" style="margin:0 auto 16px auto; width:56px; height:56px; background:rgba(255,255,255,0.22); border-radius:18px;">
                <tr>
                  <td align="center" valign="middle" style="text-align:center; vertical-align:middle; font-size:28px; line-height:56px; height:56px; width:56px;">
                    ✉️
                  </td>
                </tr>
              </table>

              <h1 style="margin:0; font-size:1.5rem; font-weight:900; color:#FFFFFF;
                         letter-spacing:-0.03em; line-height:1.2;">
                Verifica tu correo
              </h1>
              <p style="margin:8px 0 0; font-size:0.9rem; color:rgba(255,255,255,0.88);">
                Hola <strong>{nombre}</strong>, aquí está tu código de acceso
              </p>
            </td>
          </tr>

          <!-- Cuerpo -->
          <tr>
            <td style="padding:32px 40px 28px;">
              <p style="margin:0 0 20px; font-size:0.95rem; color:#444; line-height:1.6;">
                Ingresa el siguiente código en la ventana de verificación para confirmar
                tu dirección de correo y activar tu cuenta en <strong>COTIZAPro</strong>:
              </p>

              <!-- Código OTP -->
              <div style="text-align:center; margin-bottom:24px;">
                {digitos_html}
              </div>

              <!-- Info Expiración -->
              <div style="background:#FFF5F2; border:1.5px solid rgba(255,107,53,0.25);
                          border-radius:14px; padding:12px 18px; margin-bottom:24px;
                          display:flex; align-items:center; gap:10px;">
                <span style="font-size:1.1rem;">⏱️</span>
                <span style="font-size:0.84rem; color:#664; line-height:1.5;">
                  Este código es válido por <strong style="color:#c94e1e;">10 minutos</strong>.
                </span>
              </div>

              <!-- Beneficios de Prueba Gratis -->
              <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:16px; padding:20px; margin-bottom:24px;">
                <h4 style="margin:0 0 10px; font-size:0.92rem; font-weight:800; color:#111827; display:flex; align-items:center; gap:6px;">
                  🎁 ¡Tu cuenta incluye 5 cotizaciones 100% gratis!
                </h4>
                <p style="margin:0 0 12px; font-size:0.84rem; color:#4B5563; line-height:1.5;">
                  Al completar la verificación, tendrás acceso inmediato a:
                </p>
                <ul style="margin:0; padding-left:18px; font-size:0.84rem; color:#374151; line-height:1.7;">
                  <li>📄 <strong>Cotizaciones en PDF:</strong> Diseños profesionales listos para enviar.</li>
                  <li>📲 <strong>Envío por WhatsApp:</strong> Comparte presupuestos en 1 clic.</li>
                  <li>🏢 <strong>Perfil de Empresa:</strong> Personaliza con tu logo y datos de contacto.</li>
                </ul>
              </div>

              <!-- Canal de Soporte por WhatsApp -->
              <div style="background:#F0FDF4; border:1px solid rgba(16,185,129,0.3); border-radius:14px; padding:14px 18px; margin-bottom:24px;">
                <div style="font-size:0.86rem; color:#065F46; line-height:1.5; display:flex; align-items:center; gap:8px;">
                  <span style="font-size:1.2rem;">💬</span>
                  <div>
                    <strong>¿Necesitas ayuda o tienes consultas?</strong><br>
                    Contáctanos por WhatsApp al <a href="https://wa.me/59172125280" style="color:#059669; font-weight:800; text-decoration:none;">+591 72125280</a> o respondiendo a este correo.
                  </div>
                </div>
              </div>

              <!-- Aviso de seguridad -->
              <p style="margin:0; font-size:0.78rem; color:#9CA3AF; line-height:1.5; text-align:center;">
                🔒 Por razones de seguridad, <strong>nunca compartas este código</strong> con nadie.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#FAFAFA; border-top:1px solid #F3F4F6;
                       padding:20px 40px; text-align:center;">
              <p style="margin:0; font-size:0.8rem; color:#6B7280; font-weight:700;">
                📍 COTIZAPro · Bolivia
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>
"""



def enviar_codigo_verificacion(correo: str, codigo: str, nombre: str = 'Usuario') -> bool:
    """
    Envía el código OTP al correo dado.

    Returns:
        True  → email enviado con éxito
        False → fallo en el envío (ver logs del servidor)
    """
    mail_server   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    mail_port     = int(os.environ.get('MAIL_PORT', '587'))
    mail_username = os.environ.get('MAIL_USERNAME', '').strip()
    mail_password = os.environ.get('MAIL_PASSWORD', '').strip()
    mail_from_name = os.environ.get('MAIL_FROM_NAME', 'COTIZAPro')


    if not mail_username or not mail_password:
        # ── Modo Desarrollo ──────────────────────────────────────────────────
        print("=" * 60)
        print(f"[DEV EMAIL] Código de verificación para: {correo}")
        print(f"[DEV EMAIL] Nombre: {nombre}")
        print(f"[DEV EMAIL] *** CÓDIGO OTP: {codigo} ***")
        print(f"[DEV EMAIL] (Configura MAIL_USERNAME y MAIL_PASSWORD en .env para enviar emails reales)")
        print("=" * 60)
        return True

    # ── Construir el mensaje MIME ────────────────────────────────────────────
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'🔐 Tu código de verificación COTIZAPro: {codigo}'
    msg['From']    = f'{mail_from_name} <{mail_username}>'
    msg['To']      = correo


    # Parte texto plano (fallback para clientes sin HTML)
    texto_plano = (
        f"Hola {nombre},\n\n"
        f"Tu código de verificación de COTIZAPro es:\n\n"
        f"  {codigo}\n\n"
        f"Este código es válido por 10 minutos.\n"
        f"Si no solicitaste esto, ignora este mensaje.\n\n"
        f"-- COTIZAPro"
    )
    msg.attach(MIMEText(texto_plano, 'plain', 'utf-8'))
    msg.attach(MIMEText(_build_email_html(nombre, codigo), 'html', 'utf-8'))

    # ── Enviar via SMTP con TLS ──────────────────────────────────────────────
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(mail_server, mail_port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(mail_username, mail_password)
            server.sendmail(mail_username, correo, msg.as_string())
        print(f"[EMAIL] Código OTP enviado exitosamente a: {correo}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(f"[EMAIL ERROR] Autenticación SMTP fallida. Verifica MAIL_USERNAME y MAIL_PASSWORD.")
        return False
    except smtplib.SMTPException as e:
        print(f"[EMAIL ERROR] Error SMTP: {e}")
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] Error inesperado al enviar email: {e}")
        return False

