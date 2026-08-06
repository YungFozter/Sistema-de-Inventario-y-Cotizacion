# ============================================================
# SERVICIO DE TIPO DE CAMBIO PARALELO (BOLIVIA) - COTIZAPro
# ============================================================
import time
import logging
import requests

# Caché en memoria para evitar peticiones redundantes
_cache_tipo_cambio = {
    'rate': 9.50, # Tipo de cambio paralelo por defecto en Bolivia (Bs/USD)
    'last_updated': 0,
    'ttl': 900 # 15 minutos de vigencia en caché
}

def obtener_tipo_cambio_paralelo_bolivia():
    """
    Devuelve el valor actual del Tipo de Cambio Paralelo en Bolivia (Bs por cada $USD).
    Utiliza caché de 15 minutos y fallback resiliente.
    """
    ahora = time.time()
    if ahora - _cache_tipo_cambio['last_updated'] < _cache_tipo_cambio['ttl']:
        return _cache_tipo_cambio['rate']

    try:
        # Petición a API pública de cotizaciones P2P/Paralelo Bolivia (Binance / DolarBolivia)
        # Timeout corto de 2.5s para no demorar la respuesta de la aplicación
        resp = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=USDTBOB', timeout=2.5)
        if resp.status_code == 200:
            data = resp.json()
            val = float(data.get('price', 0))
            if 6.0 <= val <= 25.0: # Rango de cordura
                _cache_tipo_cambio['rate'] = round(val, 2)
                _cache_tipo_cambio['last_updated'] = ahora
                return _cache_tipo_cambio['rate']
    except Exception as e:
        logging.warning(f"No se pudo consultar el servicio en vivo de tipo de cambio paralelo: {e}")

    # Si falla la consulta remota, retornar la cotización guardada en caché o fallback
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
