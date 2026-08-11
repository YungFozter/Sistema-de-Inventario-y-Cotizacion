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

            # Si la línea empieza con un número de item o código (ej: "1 6232 ...", "1 ELE-101 ...", "1. PROD-01 ...")
            if re.match(r'^\d{1,3}[\.\s]+[A-Za-z0-9\-\.\_\/]{2,}', line_clean):
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
                text_after_price = []
                if clean_p_tokens:
                    # El primer token que parezca un número se considera precio
                    first_tok = clean_p_tokens[0]
                    if re.match(r'^[0-9.,\-]+$', first_tok):
                        precio_val = cls._clean_price(first_tok)
                        text_after_price = clean_p_tokens[1:]
                    else:
                        text_after_price = clean_p_tokens

                before_um = tokens[:um_idx]

                # Extraer la cantidad si hay un número entero o decimal justo antes de la U/M
                cantidad_val = 1.0
                if before_um and re.match(r'^\d+(?:[\.,]\d+)?$', before_um[-1]):
                    raw_qty = before_um.pop().replace(',', '.')
                    try:
                        cantidad_val = float(raw_qty)
                    except ValueError:
                        cantidad_val = 1.0
                        
                # Si había texto después del precio, lo añadimos para evaluarlo como descripción/marca
                if text_after_price:
                    before_um.extend(text_after_price)

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
    def parse_structured_tables(cls, pdf_file, consolidar_duplicados=True):
        """Extrae tablas estructuradas de PDF y captura columnas personalizadas en campos_personalizados"""
        products = []
        try:
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        # Buscar las cabeceras en las primeras 4 filas de la tabla
                        header_row_idx = 0
                        cod_idx = -1
                        desc_idx = -1
                        marca_idx = -1
                        cant_idx = -1
                        um_idx = -1
                        precio_idx = -1
                        custom_map = {}
                        
                        skip_keywords = ['n°', 'nº', 'no.', 'item', '#', 'total', 'subtotal', 'n °']

                        for r_idx, row in enumerate(table[:15]):
                            if not row: continue
                            headers = [re.sub(r'\s+', ' ', str(h).replace('\n', ' ')).strip() if h else '' for h in row]
                            norm_headers = [h.lower() for h in headers]
                            
                            c_idx = -1; d_idx = -1; m_idx = -1; ca_idx = -1; u_idx = -1; p_idx = -1
                            
                            for idx, h in enumerate(norm_headers):
                                if any(k in h for k in ['codigo', 'cod', 'código', 'id']) and c_idx == -1: c_idx = idx
                                elif any(k in h for k in ['descripcion', 'descripción', 'producto', 'detalle', 'articulo', 'artículo', 'nombre', 'material', 'item', 'concepto', 'designacion', 'designación', 'desc', 'art', 'prod']) and d_idx == -1: d_idx = idx
                                elif any(k in h for k in ['marca', 'fabricante', 'brand']) and m_idx == -1: m_idx = idx
                                elif any(k in h for k in ['cant', 'cantidad', 'qty']) and ca_idx == -1: ca_idx = idx
                                elif any(k in h for k in ['u/m', 'um', 'unidad', 'medida', 'u.m']) and u_idx == -1: u_idx = idx
                                elif any(k in h for k in ['precio', 'p. unit', 'p.unit', 'unitario', 'p/unit', 'p.u', 'p/u', 'p. u.', 'p/u (bs)']) and p_idx == -1: p_idx = idx
                            
                            # Si encuentra al menos Código o Descripción, asumimos que es la fila de cabeceras
                            if c_idx != -1 or d_idx != -1:
                                header_row_idx = r_idx
                                cod_idx = c_idx
                                desc_idx = d_idx
                                marca_idx = m_idx
                                cant_idx = ca_idx
                                um_idx = u_idx
                                precio_idx = p_idx
                                
                                for idx, h in enumerate(norm_headers):
                                    if h and idx not in (cod_idx, desc_idx, marca_idx, cant_idx, um_idx, precio_idx) and not any(sk in h for sk in skip_keywords):
                                        header_title = re.sub(r'\s+', ' ', headers[idx]).title()
                                        custom_map[idx] = header_title
                                break
                                
                        # Si no se encontraron por cabecera, usar inferencia de tipos de datos en las primeras filas de datos
                        if cod_idx == -1 or desc_idx == -1:
                            scores = {'cod': {}, 'desc': {}, 'marca': {}, 'um': {}, 'cant': {}, 'precio': {}}
                            num_cols = max((len(r) for r in table[header_row_idx + 1:header_row_idx + 6] if r), default=0)
                            
                            if num_cols >= 3:
                                for col in range(num_cols):
                                    for key in scores: scores[key][col] = 0
                                    
                                for row in table[header_row_idx + 1:header_row_idx + 6]:
                                    if not row or len(row) < num_cols: continue
                                    for col, cell in enumerate(row[:num_cols]):
                                        val = str(cell).strip()
                                        if not val: continue
                                        val_upper = val.upper()
                                        
                                        if val_upper in cls.KNOWN_UMS:
                                            scores['um'][col] += 10
                                            
                                        is_num = bool(re.match(r'^[\d\.,\-]+$', val))
                                        has_currency = bool(re.search(r'(?i)(bs|usd|\$|€|bs\.)', val))
                                        
                                        if is_num or has_currency:
                                            try:
                                                num_val = float(re.sub(r'[^\d\.]', '', val.replace(',', '.')))
                                                if has_currency: scores['precio'][col] += 5
                                                if num_val > 0:
                                                    if num_val < 1000 and float(num_val).is_integer() and col > 0:
                                                        scores['cant'][col] += 2
                                                    if has_currency or (not float(num_val).is_integer() and col > 0):
                                                        scores['precio'][col] += 2
                                            except: pass
                                            
                                        if len(val) >= 2 and len(val) <= 25 and ' ' not in val:
                                            if col == 0 and re.match(r'^\d+$', val) and int(val) < 100:
                                                pass
                                            else:
                                                scores['cod'][col] += 3
                                                
                                        if len(val) > 15 and ' ' in val:
                                            scores['desc'][col] += 5
                                            
                                used_cols = set()
                                for p in ['desc', 'um', 'precio', 'cant', 'cod']:
                                    best_c = -1
                                    best_s = 0
                                    for c, s in scores[p].items():
                                        if c not in used_cols and s > best_s:
                                            best_s = s
                                            best_c = c
                                    if best_c != -1:
                                        if p == 'desc' and desc_idx == -1: desc_idx = best_c
                                        elif p == 'um' and um_idx == -1: um_idx = best_c
                                        elif p == 'precio' and precio_idx == -1: precio_idx = best_c
                                        elif p == 'cant' and cant_idx == -1: cant_idx = best_c
                                        elif p == 'cod': cod_idx = best_c  # Siempre sobrescribir cod si la inferencia encuentra uno mejor (evita atrapar la columna #)
                                        used_cols.add(best_c)
                                        
                                # Limpiar de custom_map los inferidos
                                for inferred_idx in (cod_idx, desc_idx, marca_idx, cant_idx, um_idx, precio_idx):
                                    if inferred_idx in custom_map:
                                        del custom_map[inferred_idx]

                        if cod_idx == -1 and desc_idx == -1:
                            continue

                        for row in table[header_row_idx + 1:]:
                            if not row or len(row) < 3:
                                continue
                            
                            row_cells = [re.sub(r'\s+', ' ', str(c).replace('\n', ' ')).strip() if c else '' for c in row]
                            
                            cod = row_cells[cod_idx] if cod_idx != -1 and cod_idx < len(row_cells) else ''
                            desc = row_cells[desc_idx] if desc_idx != -1 and desc_idx < len(row_cells) else ''
                            marca = row_cells[marca_idx] if marca_idx != -1 and marca_idx < len(row_cells) else ''
                            um = row_cells[um_idx] if um_idx != -1 and um_idx < len(row_cells) else 'PZA'

                            try:
                                cant_str = row_cells[cant_idx].replace(',', '.') if cant_idx != -1 and cant_idx < len(row_cells) else '1'
                                cant = float(cant_str) if cant_str else 1.0
                            except ValueError:
                                cant = 1.0

                            try:
                                precio_str = re.sub(r'[^\d\.]', '', row_cells[precio_idx].replace(',', '.')) if precio_idx != -1 and precio_idx < len(row_cells) else '0'
                                precio = float(precio_str) if precio_str else 0.0
                            except ValueError:
                                precio = 0.0

                            campos_pers = {}
                            for c_idx, c_name in custom_map.items():
                                if c_idx < len(row_cells) and row_cells[c_idx]:
                                    campos_pers[c_name] = row_cells[c_idx]

                            if cod or desc:
                                products.append({
                                    'codigo': cod,
                                    'descripcion': desc,
                                    'marca': marca,
                                    'um': um,
                                    'cantidad': cant,
                                    'precio_unitario': precio,
                                    'precio_total': round(cant * precio, 2),
                                    'campos_personalizados': campos_pers
                                })
        except Exception:
            pass

        if not products:
            return []

        if not consolidar_duplicados:
            return products

        consolidated = {}
        for p in products:
            cod = p['codigo'] or p['descripcion']
            if cod in consolidated:
                consolidated[cod]['cantidad'] = round(consolidated[cod]['cantidad'] + p['cantidad'], 2)
                consolidated[cod]['precio_total'] = round(consolidated[cod]['cantidad'] * consolidated[cod]['precio_unitario'], 2)
                if p.get('campos_personalizados'):
                    consolidated[cod]['campos_personalizados'].update(p['campos_personalizados'])
            else:
                consolidated[cod] = dict(p)

        return list(consolidated.values())

    @classmethod
    def extract_products(cls, pdf_source, consolidar_duplicados=True):
        """Procesa el PDF obteniendo las líneas y aplicando la parseación de bloques"""
        try:
            if isinstance(pdf_source, bytes):
                pdf_file = BytesIO(pdf_source)
            else:
                pdf_file = pdf_source

            # Intento 1: Parseo de tablas estructuradas capturando campos personalizados
            struct_prods = cls.parse_structured_tables(pdf_file, consolidar_duplicados=consolidar_duplicados)
            if struct_prods:
                return struct_prods

            # Intento 2: Parseo de texto por líneas
            if isinstance(pdf_source, bytes):
                pdf_file.seek(0)

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

            # Intento 3: Respado con extract_tables y parse_raw_lines
            if isinstance(pdf_source, bytes):
                pdf_file.seek(0)

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


