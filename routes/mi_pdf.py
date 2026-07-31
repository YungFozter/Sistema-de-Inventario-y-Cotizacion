from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from utils.decorators import login_required
from models import obtener_configuracion_pdf, guardar_configuracion_pdf

mi_pdf_bp = Blueprint('mi_pdf', __name__)

def register_mi_pdf_routes(app):
    @app.route('/mi-pdf', methods=['GET'])
    @login_required
    def mi_pdf_index():
        usuario_id = session.get('user_id')
        config_pdf = obtener_configuracion_pdf(usuario_id)
        return render_template('mi_pdf.html', config_pdf=config_pdf)

    @app.route('/mi-pdf/guardar', methods=['POST'])
    @login_required
    def mi_pdf_guardar():
        usuario_id = session.get('user_id')
        data = request.json or request.form
        
        datos = {
            'tipo_hoja': data.get('tipo_hoja', 'A4'),
            'color_tema': data.get('color_tema', '#dc2626'),
            'titulo_documento': data.get('titulo_documento', 'COTIZACIÓN DE VENTAS'),
            'empresa_nombre': data.get('empresa_nombre', ''),
            'nit_emisor': data.get('nit_emisor', ''),
            'telefono': data.get('telefono', ''),
            'correo': data.get('correo', ''),
            'direccion': data.get('direccion', ''),
            'terminos_condiciones': data.get('terminos_condiciones', ''),
            'nota_pie': data.get('nota_pie', ''),
            'responsable_nombre': data.get('responsable_nombre', ''),
            'responsable_telefono': data.get('responsable_telefono', ''),
            'responsable_email': data.get('responsable_email', ''),
            'plazo_entrega': data.get('plazo_entrega', ''),
            'logo_base64': data.get('logo_base64', '')
        }
        
        exito = guardar_configuracion_pdf(usuario_id, datos)
        if exito:
            return jsonify({'success': True, 'message': 'Configuración de PDF guardada exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al guardar la configuración'}), 500
