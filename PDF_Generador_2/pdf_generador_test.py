"""
pdf_generador_test.py
Script de prueba visual para PDF_Generador_2.
Genera un PDF con datos de prueba y exporta cada página a PNG para validación visual.
"""
import os
import sys

# Agregar la raíz del proyecto al path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PDF_Generador_2 import generar_cotizacion_pdf_v2
import pypdfium2 as pdfium

datos_demo = {
    'cliente': {
        'nombre': "SANTIAGO MENDOZA SORIA",
        'nit': "1029384756",
        'telefono': "71234567",
        'email': "ieeimendoza@gmail.com"
    },
    'cotizacion': {
        'solicitud_numero': "2026-001",
        'fecha': "17/10/2026",
        'validez': "1 Día",
        'moneda': "Bolivianos (Bs)"
    },
    'productos': [
        {
            'codigo': "C-8045",
            'descripcion': "CABLE NEXANS FITER FLEX HEPR (90°C) 0.6/1KV 4 X 2.5 MM2",
            'marca': "NEXANS",
            'cantidad': 25,
            'um': "MTS",
            'precio_unitario': 28.71,
            'subtotal': 717.75
        },
        {
            'codigo': "C-12143",
            'descripcion': "CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 6 MM2",
            'marca': "NEXANS",
            'cantidad': 50,
            'um': "MTS",
            'precio_unitario': 13.88,
            'subtotal': 694.00
        },
        {
            'codigo': "T-11343",
            'descripcion': "TERMINAL OJAL AMARILLO KSN 4-6 MM2 DIAM 6.5MM",
            'marca': "KASAN",
            'cantidad': 12,
            'um': "PZA",
            'precio_unitario': 0.48,
            'subtotal': 5.76
        },
        {
            'codigo': "CN-17244",
            'descripcion': "CONECTOR CONDUIT BOQUILLA ACERO HNYSN C/ROSCA Y PERNO 1\"",
            'marca': "HANYSEN",
            'cantidad': 14,
            'um': "PZA",
            'precio_unitario': 6.91,
            'subtotal': 96.74
        },
        {
            'codigo': "J-400",
            'descripcion': "JABALINA CU Z HUADIANG 5/8\" X 2,40 MTS",
            'marca': "HUADIANG",
            'cantidad': 1,
            'um': "PZA",
            'precio_unitario': 70.10,
            'subtotal': 70.10
        }
    ],
    'subtotal': 1584.35,
    'descuento_porcentaje': 0.0,
    'monto_descuento': 0.0,
    'total': 1584.35,
    'total_letras': "MIL QUINIENTOS OCHENTA Y CUATRO BOLIVIANOS CON 35/100",
    'usuario_sesion': "Santiago Mendoza Soria",
    'usuario': {
        'nombre': "Santiago Mendoza Soria",
        'telefono': "71234567",
        'email': "ieeimendoza@gmail.com"
    }
}

if __name__ == '__main__':
    print("Iniciando prueba de generación con PDF_Generador_2...")
    pdf_bytes = generar_cotizacion_pdf_v2(datos_demo)

    # Guardar PDF de prueba
    output_pdf_path = os.path.join(ROOT_DIR, 'scratch', 'test_v2_cotizacion.pdf')
    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
    with open(output_pdf_path, 'wb') as f:
        f.write(pdf_bytes)
    print(f"[OK] PDF guardado en: {output_pdf_path} ({len(pdf_bytes)} bytes)")

    # Renderizar imagen PNG para verificación visual inmediata
    doc = pdfium.PdfDocument(pdf_bytes)
    print(f"[OK] Total de paginas generadas: {len(doc)}")

    for idx, page in enumerate(doc):
        img = page.render(scale=1.5).to_pil()
        output_png_path = os.path.join(ROOT_DIR, 'scratch', f'test_v2_page_{idx + 1}.png')
        img.save(output_png_path)
        print(f"[OK] Vista previa renderizada en: {output_png_path}")

    print("Prueba completada con exito.")
