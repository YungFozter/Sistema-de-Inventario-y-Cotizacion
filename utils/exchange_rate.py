# ============================================================
# SERVICIO DE TIPO DE CAMBIO PARALELO (BOLIVIA) - COTIZAPro
# ============================================================
import time
import logging
import requests

# Caché en memoria para evitar peticiones redundantes
_cache_tipo_cambio = {
    'rate': 10.32, # Cotización AirTM / Paralelo por defecto (Bs/USD)
    'last_updated': 0,
    'ttl': 900 # 15 minutos de vigencia en caché
}

def obtener_tipo_cambio_paralelo_bolivia():
    """
    Devuelve el valor actual del Tipo de Cambio Paralelo en Bolivia (Bs por cada $USD).
    Sincroniza con servicios P2P/AirTM en tiempo real con caché de 15 minutos.
    """
    ahora = time.time()
    if ahora - _cache_tipo_cambio['last_updated'] < _cache_tipo_cambio['ttl']:
        return _cache_tipo_cambio['rate']

    try:
        # Petición al servicio de cotizaciones P2P/AirTM/Paralelo en tiempo real (Yadio / AirTM)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) COTIZAPro/2.0'}
        resp = requests.get('https://api.yadio.io/rate/BOB/USD', headers=headers, timeout=3.5)
        if resp.status_code == 200:
            data = resp.json()
            val = float(data.get('rate', 0))
            if 7.0 <= val <= 25.0: # Rango de cordura para Bolivia
                _cache_tipo_cambio['rate'] = round(val, 2)
                _cache_tipo_cambio['last_updated'] = ahora
                return _cache_tipo_cambio['rate']
    except Exception as e:
        logging.warning(f"No se pudo consultar el servicio en vivo de tipo de cambio paralelo: {e}")

    # Si falla la consulta remota, retornar la cotización guardada en caché o fallback (10.32)
    return _cache_tipo_cambio['rate']

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
