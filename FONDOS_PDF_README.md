# Configuración de Fondos Dinámicos para PDFs de Cotizaciones

## Descripción
El sistema aplica automáticamente diferentes imágenes de fondo según el número de páginas de cada cotización PDF generada.

## Imágenes Requeridas
Todas las imágenes deben estar en `static/images/`:

1. **FondoCotizacion.png** (349.7 KB)
   - Uso: Páginas únicas (cotizaciones de 1 sola página)
   - Formato: PNG
   - Ubicación: `static/images/FondoCotizacion.png`

2. **FondoCotizacion2.png** (~162.4 KB)
   - Uso: Primera página cuando hay exactamente 2 páginas
   - Formato: PNG
   - Ubicación: `static/images/FondoCotizacion2.png`

3. **FondoCotizacionHojaMedia.png** (116.6 KB)
   - Uso: Páginas intermedias en cotizaciones de 3 o más páginas
   - Formato: PNG  
   - Ubicación: `static/images/FondoCotizacionHojaMedia.png`

4. **FondoCotizacionHojaFinal.png** (187.4 KB)
   - Uso: Última página en cotizaciones de 2 o más páginas
   - Formato: PNG
   - Ubicación: `static/images/FondoCotizacionHojaFinal.png`

## Lógica de Aplicación

### Cotización de 1 Página
```
Página 1: FondoCotizacion.png
```

### Cotización de 2 Páginas (Caso Especial)
```
Página 1: FondoCotizacion2.png
Página 2: FondoCotizacionHojaFinal.png
```

### Cotización de Múltiples Páginas (3 o más)
```
Página 1: FondoCotizacion2.png
Página 2: FondoCotizacionHojaMedia.png
Página 3: FondoCotizacionHojaMedia.png
...
Página N-1: FondoCotizacionHojaMedia.png
Página N: FondoCotizacionHojaFinal.png
```

## Ejemplos

### 2 Páginas
```
[FondoCotizacion2.png, FondoCotizacionHojaFinal.png]
```

### 3 Páginas  
```
[FondoCotizacion2.png, FondoCotizacionHojaMedia.png, FondoCotizacionHojaFinal.png]
```

### 4 Páginas
```
[FondoCotizacion2.png, FondoCotizacionHojaMedia.png, FondoCotizacionHojaMedia.png, FondoCotizacionHojaFinal.png]
```

### 5 Páginas
```
[FondoCotizacion2.png, HojaMedia, HojaMedia, HojaMedia, HojaFinal]
```

## Características Adicionales

- **Márgenes dinámicos**: Las páginas 2+ tienen margen superior ampliado (15mm vs 10mm) para mejor estética
- **Logging detallado**: Cada aplicación de fondo genera logs para diagnóstico
- **Fallback robusto**: Si una imagen no existe, usa `FondoCotizacion.png` como respaldo
- **Manejo de errores**: En caso de error, genera PDF sin fondo en lugar de fallar

## Verificación
Ejecutar `test_nuevas_imagenes.py` para verificar que todas las imágenes están presentes y correctamente configuradas.

## Logs Esperados
Al generar un PDF verás mensajes como:

### Para 1 página:
```
=== GENERANDO PDF COTIZACIÓN X ===
=== INICIANDO APLICACIÓN DE FONDOS ===
✓ FondoCotizacion.png encontrado, tamaño: 349732 bytes
Procesando página 1 con FondoCotizacion.png (página única)
```

### Para 2 páginas:
```
=== GENERANDO PDF COTIZACIÓN X ===
=== INICIANDO APLICACIÓN DE FONDOS ===
✓ FondoCotizacion2.png encontrado, tamaño: 162365 bytes
✓ FondoCotizacionHojaFinal.png encontrado, tamaño: 187446 bytes
Procesando página 1 con FondoCotizacion2.png (primera de 2 páginas)
Procesando página 2 con FondoCotizacionHojaFinal.png (segunda de 2 páginas)
```

### Para 3+ páginas:
```
=== GENERANDO PDF COTIZACIÓN X ===
=== INICIANDO APLICACIÓN DE FONDOS ===
✓ FondoCotizacion2.png encontrado, tamaño: 162365 bytes
✓ FondoCotizacionHojaMedia.png encontrado, tamaño: 116596 bytes  
✓ FondoCotizacionHojaFinal.png encontrado, tamaño: 187446 bytes
Procesando página 1 con FondoCotizacion2.png (primera de múltiples páginas)
Procesando página 2 con FondoCotizacionHojaMedia.png (página intermedia)
Procesando página 3 con FondoCotizacionHojaFinal.png (página final)
```