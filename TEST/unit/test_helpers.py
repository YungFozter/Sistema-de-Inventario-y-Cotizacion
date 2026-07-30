from utils.helpers import format_date
from datetime import datetime

def test_format_date_string():
    # El filtro recibe strings o datetimes
    date_str = "2023-10-15 14:30:00"
    formatted = format_date(date_str)
    assert formatted == "15/10/2023"

def test_format_date_datetime():
    dt = datetime(2023, 10, 15, 14, 30)
    formatted = format_date(dt)
    assert formatted == "15/10/2023"

def test_format_date_none():
    assert format_date(None) == ""

from utils.pdf_extractor import PDFProductExtractor

def test_parse_multiline_description():
    lines = [
        "2 12143 CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 6 MM2",
        "NEGRO NEXANS BRASIL 50 MTS BS 13.88 BS 694"
    ]
    products = PDFProductExtractor.parse_raw_lines(lines, consolidar_duplicados=False)
    assert len(products) == 1
    p = products[0]
    assert p['codigo'] == '12143'
    assert p['descripcion'] == 'CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 6 MM2 NEGRO'
    assert p['marca'] == 'NEXANS'
    assert p['um'] == 'MTS'
    assert p['cantidad'] == 50.0
    assert p['precio_unitario'] == 13.88

def test_parse_12_items_pdf():
    lines = [
        "1 8045 CABLE NEXANS FITER FLEX HEPR (90°C) 0.6/1KV 4 X 2.5 MM2 NEXANS BRASIL 25 MTS BS 28.71 BS 717.75",
        "2 12143 CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 6 MM2",
        "NEGRO NEXANS BRASIL 50 MTS BS 13.88 BS 694",
        "3 12845 CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 4 MM2",
        "VERDE/AMARILLO NEXANS BRASIL 15 MTS BS 9.56 BS 143.4",
        "4 11343 TERMINAL OJAL AMARILLO KSN 4-6 MM2 DIAM 6.5MM RV5.5-6 KASAN CN 12 PZA BS 0.48 BS 5.76",
        "5 11341 TERMINAL OJAL AZUL KSN 1.5-2.5 MM2 DIAM 6.5MM RVS2-6 KASAN CN 40 PZA BS 0.22 BS 8.8",
        "6 17244 CONECTOR CONDUIT BOQUILLA ACERO HNYSN C/ROSCA Y",
        "PERNO 1\" S3100 HANYSEN CHINA 14 PZA BS 6.91 BS 96.74",
        "7 4748 CONECTOR PRENSACABLE HJA PG-16 HJA TAIWAN 8 PZA BS 2.39 BS 19.12",
        "8 400 JABALINA CU Z HUADIANG 5/8\" X 2,40 MTS Z HUADIANG 1 PZA BS 70.1 BS 70.1",
        "9 587 CABLE DESNUDO DE CU 25 MM2 7 HILOS INDUSCABOS BRASIL 4 MTS BS 59.35 BS 237.4",
        "10 317 CONECTOR P/JABALINA Z HUADIANG DE 5/8\" Z HUADIANG 1 PZA BS 17.67 BS 17.67",
        "11 11327 TERMINAL PUNTA HUECA KSN 6 MM2 ROJO E6012 KASAN CN 100 PZA BS 0.22 BS 22",
        "12 11325 TERMINAL PUNTA HUECA KSN 2.5 MM2 AZUL E2512 KASAN CN 100 PZA BS 0.14 BS 14",
        "SON: Mil ochocientos cuarenta y dos Bolivianos con Siete Centavos Subtotal BS 2,046.74"
    ]
    products = PDFProductExtractor.parse_raw_lines(lines, consolidar_duplicados=False)
    assert len(products) == 12
    codigos = [p['codigo'] for p in products]
    assert codigos == ['8045', '12143', '12845', '11343', '11341', '17244', '4748', '400', '587', '317', '11327', '11325']
