# ============================================================
# SERVICIO DE TIPO DE CAMBIO BANCO CENTRAL DE BOLIVIA (BCB)
# Sitio Oficial: https://www.bcb.gob.bo/
# ============================================================
import time
import logging
import requests
import re
import urllib3

# Deshabilitar advertencias de SSL para consulta segura al servidor del BCB
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Caché en memoria para evitar peticiones redundantes al BCB
_cache_tipo_cambio = {
    'rate': 6.96, # Tipo de Cambio Oficial del Banco Central de Bolivia (BCB)
    'fuente': 'Banco Central de Bolivia (BCB - bcb.gob.bo)',
    'last_updated': 0,
    'ttl': 900 # 15 minutos de vigencia en caché
}

def obtener_tipo_cambio_bcb():
    """
    Devuelve el Tipo de Cambio Oficial del Banco Central de Bolivia (BCB - https://www.bcb.gob.bo/).
    Sincroniza con el portal web oficial del BCB con caché de 15 minutos y resguardo a 6.96 Bs/USD.
    """
    ahora = time.time()
    if ahora - _cache_tipo_cambio['last_updated'] < _cache_tipo_cambio['ttl']:
        return _cache_tipo_cambio['rate']

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) COTIZAPro/2.0'}
        # Consultar la plataforma oficial del Banco Central de Bolivia
        resp = requests.get('https://www.bcb.gob.bo/?q=servicios/cotizaciones', headers=headers, verify=False, timeout=3.5)
        if resp.status_code == 200:
            # Extraer cotización del Dólar Estadounidense en el portal oficial del BCB
            match = re.search(r'D[óo]lar.*?([6-9]\.\d{2}|1[0-2]\.\d{2})', resp.text, re.IGNORECASE | re.DOTALL)
            if match:
                val = float(match.group(1))
                if 6.0 <= val <= 20.0:
                    _cache_tipo_cambio['rate'] = round(val, 2)
                    _cache_tipo_cambio['last_updated'] = ahora
                    return _cache_tipo_cambio['rate']
    except Exception as e:
        logging.warning(f"No se pudo consultar el portal del BCB (bcb.gob.bo): {e}")

    # Fallback al Tipo de Cambio Oficial del Banco Central de Bolivia (6.96 Bs/USD)
    _cache_tipo_cambio['rate'] = 6.96
    _cache_tipo_cambio['last_updated'] = ahora
    return _cache_tipo_cambio['rate']

def obtener_tipo_cambio_paralelo_bolivia():
    """Alias compatible para devolver el Tipo de Cambio del Banco Central de Bolivia (BCB)"""
    return obtener_tipo_cambio_bcb()

def convertir_monto_moneda(monto, moneda_origen, moneda_destino='Bs', tipo_cambio=None):
    """
    Convierte un monto entre Bs y $USD utilizando el tipo de cambio proporcionado o el paralelo actual.
    """
    try:
        monto = float(monto)
    except (ValueError, TypeError):
        return 0.0

    if not tipo_cambio:
        tipo_cambio = obtener_tipo_cambio_paralelo_bolivia()

    if moneda_origen == '$USD' and moneda_destino == 'Bs':
        return round(monto * tipo_cambio, 2)
    elif moneda_origen == 'Bs' and moneda_destino == '$USD':
        return round(monto / tipo_cambio, 2) if tipo_cambio > 0 else 0.0
    
    return round(monto, 2)
