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
        "2 12143 CABLE FLEX NEXANS ECOLOGICO AFITOX 70°C-750V 1 X 6 MM2 NEXANS BRASIL 50 MTS BS 13.88 BS 694",
        "NEGRO"
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
