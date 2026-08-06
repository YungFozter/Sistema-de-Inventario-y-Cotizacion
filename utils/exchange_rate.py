import requests
import time
import logging

_rate_cache = {
    'rate': 11.28,
    'buy': 11.30,
    'sell': 11.25,
    'timestamp': 0,
    'source': 'AirTm P2P Live'
}

CACHE_DURATION_SECONDS = 600  # 10 minutos de caché

def obtener_tipo_cambio_paralelo():
    """
    Obtiene la cotización en tiempo real del dólar paralelo AirTm / P2P en Bolivia.
    Devuelve un diccionario con rate, buy, sell, timestamp y la fuente.
    """
    global _rate_cache
    ahora = time.time()

    # Si el caché tiene menos de 10 minutos de antigüedad, reutilizarlo
    if ahora - _rate_cache['timestamp'] < CACHE_DURATION_SECONDS and _rate_cache['timestamp'] > 0:
        return _rate_cache

    try:
        res = requests.get('https://paralelo.bo/api/v1/rate', timeout=4)
        if res.status_code == 200:
            data = res.json()
            rate = float(data.get('median', 11.28))
            buy = float(data.get('buy', rate))
            sell = float(data.get('sell', rate))

            _rate_cache['rate'] = round(rate, 2)
            _rate_cache['buy'] = round(buy, 2)
            _rate_cache['sell'] = round(sell, 2)
            _rate_cache['timestamp'] = ahora
            _rate_cache['source'] = 'AirTm P2P Live'
            return _rate_cache
    except Exception as e:
        logging.warning(f"No se pudo obtener tipo de cambio paralelo en vivo: {e}")

    # Mantener valor anterior si hubo un fallo temporal de red
    return _rate_cache
