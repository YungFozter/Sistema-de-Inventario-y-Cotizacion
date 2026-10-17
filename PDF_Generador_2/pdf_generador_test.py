"""
pdf_generador_test.py
Script de prueba visual exhaustivo para PDF_Generador_2.
Valida los 3 escenarios de fondos dinámicos:
1. Cotización de 1 página  -> FondoCotizacion.png
2. Cotización de 2 páginas -> FondoCotizacion2.png (p1) + FondoCotizacionHojaFinal.png (p2)
3. Cotización de 3+ páginas -> FondoCotizacion2.png (p1) + FondoCotizacionHojaMedia.png (p2) + FondoCotizacionHojaFinal.png (p3)
"""
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PDF_Generador_2 import generar_cotizacion_pdf_v2
import pypdfium2 as pdfium


def generar_datos_prueba(cantidad_items: int) -> dict:
    productos = []
    for i in range(1, cantidad_items + 1):
        precio = round(15.50 + i * 2.35, 2)
        cant = i * 2
        productos.append({
            'codigo': f"C-{1000 + i}",
            'descripcion': f"PRODUCTO ITEM {i} - CABLE FLEX AFITOX 70C-750V {i}X4 MM2",
            'marca': "NEXANS" if i % 2 == 0 else "KASAN",
            'cantidad': cant,
            'um': "MTS" if i % 2 == 0 else "PZA",
            'precio_unitario': precio,
            'subtotal': round(cant * precio, 2)
        })

    subtotal = sum(p['subtotal'] for p in productos)
    return {
        'cliente': {
            'nombre': "SANTIAGO MENDOZA SORIA",
            'nit': "1029384756",
            'telefono': "71234567",
            'email': "ieeimendoza@gmail.com"
        },
        'cotizacion': {
            'solicitud_numero': f"TEST-{cantidad_items}",
            'fecha': "17/10/2026",
            'validez': "1 Día",
            'moneda': "Bolivianos (Bs)"
        },
        'productos': productos,
        'subtotal': subtotal,
        'descuento_porcentaje': 0.0,
        'monto_descuento': 0.0,
        'total': subtotal,
        'total_letras': f"TOTAL EQUIVALENTE A {subtotal:,.2f} BOLIVIANOS",
        'usuario_sesion': "Santiago Mendoza Soria",
        'usuario': {
            'nombre': "Santiago Mendoza Soria",
            'telefono': "71234567",
            'email': "ieeimendoza@gmail.com"
        }
    }


def ejecutar_prueba_escenario(nombre: str, cantidad_items: int):
    print(f"\n==========================================")
    print(f"Probando Escenario: {nombre} ({cantidad_items} items)")
    print(f"==========================================")

    datos = generar_datos_prueba(cantidad_items)
    pdf_bytes = generar_cotizacion_pdf_v2(datos)

    doc = pdfium.PdfDocument(pdf_bytes)
    total_pags = len(doc)
    print(f"[OK] Total de paginas generadas: {total_pags}")

    # Exportar imágenes PNG
    for idx, page in enumerate(doc):
        img = page.render(scale=1.5).to_pil()
        out_name = f"escenario_{cantidad_items}items_pag_{idx + 1}_de_{total_pags}.png"
        out_path = os.path.join(ROOT_DIR, 'scratch', out_name)
        img.save(out_path)
        print(f"  -> Pagina {idx + 1}: guardada en {out_path}")


if __name__ == '__main__':
    os.makedirs(os.path.join(ROOT_DIR, 'scratch'), exist_ok=True)

    # 1. Escenario 1 Hoja (5 items)
    ejecutar_prueba_escenario("1_PAGINA", 5)

    # 2. Escenario 2 Hojas (15 items)
    ejecutar_prueba_escenario("2_PAGINAS", 15)

    # 3. Escenario 3 Hojas (28 items)
    ejecutar_prueba_escenario("3_PAGINAS", 28)

    print("\n[OK] Todas las pruebas de fondos dinamicos completadas exitosamente.")
