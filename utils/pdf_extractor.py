import os
import re
import logging
from io import BytesIO

for _log_name in ['pdfminer', 'pdfminer.pdfinterp', 'pdfminer.pdfpage', 'pdfminer.converter', 'pdfminer.layout', 'PyPDF2', 'pypdf', 'pdfplumber']:
    logging.getLogger(_log_name).setLevel(logging.ERROR)

import pdfplumber

class PDFProductExtractor:
    """
    Extractor de tablas de productos desde PDF, Excel, CSV y Texto Pegado.
    Extrae con precisión matemática: Código, Descripción, Marca, U/M, Precio Unitario.
    Omite automáticamente: #, Procedencia, Cantidad, Total y metadatos.
    """

    KNOWN_COUNTRIES = [
        'ALEMANIA', 'BRASIL', 'TAIWAN', 'TAIWÁN', 'CHINA', 'MEXICO', 'MÉXICO',
        'COLOMBIA', 'UE', 'CN', 'USA', 'ESPAÑA', 'ITALIA', 'JAPON', 'JAPÓN'
    ]

    KNOWN_UMS = [
        'PZA', 'MTS', 'BOL', 'UN', 'KG', 'M', 'PZ', 'SET', 'CJ', 'CJA',
        'RROLLO', 'ROLLO', 'PAQ', 'PAR', 'LTR', 'GLN', 'JGO'
    ]

    DOCUMENT_METADATA_PHRASES = [
        'datos clientes', 'cliente/empresa', 'atención:', 'atencion:',
        'e-mail:', 'solicitud n°', 'solicitud no', 'version n°', 'version no', 'nit:',
        'direccion:', 'dirección:', 'telefono:', 'fax:', 'celular:', 'cotizacion de ventas',
        'cotización de ventas', 'la paz:', 'santa cruz:', 'cochabamba:', 'responsable y consulta',
        'ejecutivo de ventas:', 'responsable de ing:', 'condiciones', 'tiempo de validez',
        'plazo de entrega:', 'descripcion gral.', 'descripción gral.', 'informacion importante',
        'información importante', 'estimado cliente', 'banco de credito', 'banco bisa',
        'cta en bolivianos', 'cta en dolares', 'firma responsable', 'fecha de cotizacion:',
        'fecha de cotización:', 'electrored bolivia', 'central piloto', 'pasaje cite'
    ]

    @staticmethod
    def _normalize_string(s):
        if not s:
            return ""
        s = str(s).strip().lower()
        replacements = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"))
        for a, b in replacements:
            s = s.replace(a, b)
        return s

    @classmethod
    def _is_document_metadata(cls, text):
        if not text:
            return False
        norm = cls._normalize_string(text)
        for phrase in cls.DOCUMENT_METADATA_PHRASES:
            if phrase in norm:
                return True
        return False

    @classmethod
    def _clean_price(cls, val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)

        val_str = str(val).strip()
        val_str = re.sub(r'[^\d.,\-]', '', val_str)
        if not val_str:
            return 0.0

        if ',' in val_str and '.' in val_str:
            if val_str.find(',') < val_str.find('.'):
                val_str = val_str.replace(',', '')
            else:
                val_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            parts = val_str.split(',')
            if len(parts) == 2 and len(parts[1]) == 3 and int(parts[0]) > 0:
                val_str = val_str.replace(',', '')
            else:
                val_str = val_str.replace(',', '.')

        try:
            return float(val_str)
        except ValueError:
            return 0.0

    @classmethod
    def parse_raw_lines(cls, lines, consolidar_duplicados=True):
        """
        Analiza bloques de texto tabulados/copiados de PDF/Word/Excel.
        Extrae Código, Descripción, Marca, U/M, Cantidad Real y Precio Unitario.
        Consolida productos duplicados sumando sus cantidades cuando consolidar_duplicados=True.
        """
        blocks = []
        curr_block = []

        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            norm_l = cls._normalize_string(line_clean)
            if ('codigo' in norm_l or 'cod' in norm_l) and ('descripcion' in norm_l or 'detalle' in norm_l):
                continue

            if norm_l.startswith('son:') or 'subtotal' in norm_l or 'banco' in norm_l or cls._is_document_metadata(line_clean):
                if norm_l.startswith('son:') or 'subtotal' in norm_l:
                    break
                continue

            # Si la línea empieza con un número de item o código (ej: "1 6232 ..." o "1. 6232 ...")
            if re.match(r'^\d{1,3}[\.\s]+\d+', line_clean):
                if curr_block:
                    blocks.append(curr_block)
                curr_block = [line_clean]
            elif curr_block:
                curr_block.append(line_clean)

        if curr_block:
            blocks.append(curr_block)

        raw_products = []

        for b in blocks:
            full_text = ' '.join(b)
            
            m = re.match(r'^(?:\d{1,3}[\.\s]+)?([A-Za-z0-9\-\.\_\/]{2,25})\s+(.+)$', full_text)
            if not m:
                continue

            cod, rest = m.groups()
            
            if cod.lower() in ['banco', 'son', 'subtotal', 'total', 'cliente', 'nit']:
                continue

            tokens = rest.split()
            if not tokens:
                continue

            um_idx = -1
            for idx in range(len(tokens) - 1, -1, -1):
                if tokens[idx].upper() in cls.KNOWN_UMS:
                    um_idx = idx
                    break

            if um_idx != -1:
                um_val = tokens[um_idx].upper()

                price_tokens = tokens[um_idx + 1:]
                clean_p_tokens = [t for t in price_tokens if t.upper() not in ['BS', 'BS.', 'BS:', '$', 'USD']]

                precio_val = 0.0
                if clean_p_tokens:
                    precio_val = cls._clean_price(clean_p_tokens[0])

                before_um = tokens[:um_idx]

                # Extraer la cantidad si hay un número entero o decimal justo antes de la U/M (ej: 1 PZA, 1.5 MTS, 26 MTS, 30 BOL)
                cantidad_val = 1.0
                if before_um and re.match(r'^\d+(?:[\.,]\d+)?$', before_um[-1]):
                    raw_qty = before_um.pop().replace(',', '.')
                    try:
                        cantidad_val = float(raw_qty)
                    except ValueError:
                        cantidad_val = 1.0

                if before_um and before_um[-1].upper() in cls.KNOWN_COUNTRIES:
                    before_um.pop()

                if len(before_um) >= 2:
                    marca_val = before_um[-1]
                    desc_val = " ".join(before_um[:-1])
                elif len(before_um) == 1:
                    desc_val = before_um[0]
                    marca_val = ""
                else:
                    desc_val = ""
                    marca_val = ""

                raw_products.append({
                    'codigo': cod,
                    'descripcion': desc_val,
                    'marca': marca_val,
                    'um': um_val,
                    'cantidad': cantidad_val,
                    'precio_unitario': precio_val,
                    'precio_total': round(cantidad_val * precio_val, 2)
                })

        if not consolidar_duplicados:
            return raw_products

        # Consolidar duplicados por código de producto sumando las cantidades
        consolidated = {}
        for p in raw_products:
            cod = p['codigo']
            if cod in consolidated:
                consolidated[cod]['cantidad'] = round(consolidated[cod]['cantidad'] + p['cantidad'], 2)
                consolidated[cod]['precio_total'] = round(consolidated[cod]['cantidad'] * consolidated[cod]['precio_unitario'], 2)
            else:
                consolidated[cod] = dict(p)

        return list(consolidated.values())


    @classmethod
    def detectar_duplicados(cls, raw_products):
        """
        Analiza la lista de productos crudos y detecta repeticiones por código.
        Calcula las diferencias entre campos y la suma consolidada.
        """
        groups = {}
        for idx, p in enumerate(raw_products, 1):
            cod = p['codigo']
            if cod not in groups:
                groups[cod] = []
            item_copy = dict(p)
            item_copy['item_index'] = idx
            groups[cod].append(item_copy)

        duplicados = []
        for cod, items in groups.items():
            if len(items) > 1:
                cantidades = [i['cantidad'] for i in items]
                precios = [i['precio_unitario'] for i in items]
                marcas = [i['marca'] for i in items]
                ums = [i['um'] for i in items]

                total_cant = round(sum(cantidades), 2)
                total_subtotal = round(total_cant * items[0]['precio_unitario'], 2)

                diferencias = []
                if len(set(cantidades)) > 1:
                    diferencias.append('cantidad')
                if len(set(precios)) > 1:
                    diferencias.append('precio_unitario')
                if len(set(marcas)) > 1:
                    diferencias.append('marca')
                if len(set(ums)) > 1:
                    diferencias.append('um')

                duplicados.append({
                    'codigo': cod,
                    'descripcion': items[0]['descripcion'],
                    'marca': items[0]['marca'],
                    'um': items[0]['um'],
                    'precio_unitario': items[0]['precio_unitario'],
                    'total_repeticiones': len(items),
                    'cantidad_consolidada': total_cant,
                    'subtotal_consolidado': total_subtotal,
                    'diferencias_campos': diferencias,
                    'ocurrencias': items
                })

        return duplicados

    @classmethod
    def extract_products(cls, pdf_source, consolidar_duplicados=True):
        """Procesa el PDF obteniendo las líneas y aplicando la parseación de bloques"""
        try:
            if isinstance(pdf_source, bytes):
                pdf_file = BytesIO(pdf_source)
            else:
                pdf_file = pdf_source

            lines = []
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(layout=False) or ""
                    for l in text.split('\n'):
                        if l.strip():
                            lines.append(l.strip())

            prods = cls.parse_raw_lines(lines, consolidar_duplicados=consolidar_duplicados)
            if prods:
                return prods

            # Respado con extract_tables si extract_text no retorna ítems
            table_lines = []
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if not row:
                                    continue
                                cleaned_cells = [re.sub(r'\s+', ' ', str(cell).strip()) for cell in row if cell is not None and str(cell).strip()]
                                if cleaned_cells:
                                    table_lines.append(" ".join(cleaned_cells))

            return cls.parse_raw_lines(table_lines, consolidar_duplicados=consolidar_duplicados)
        except Exception as e:
            print(f"Error extrayendo PDF: {e}")
            return []

    @classmethod
    def parse_pasted_text(cls, text, consolidar_duplicados=True):
        """Procesa texto copiado y pegado desde la interfaz web"""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return cls.parse_raw_lines(lines, consolidar_duplicados=consolidar_duplicados)


