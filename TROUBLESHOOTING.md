# Solución de Problemas en la Terminal

## 🚀 Formas de Iniciar la Aplicación

### Método 1: Script PowerShell (Recomendado)
```powershell
.\start.ps1
```

### Método 2: Script Batch
```cmd
start.bat
```

### Método 3: Gestión Avanzada
```bash
# Iniciar la aplicación
python manage.py start

# Detener la aplicación
python manage.py stop

# Reiniciar la aplicación
python manage.py restart

# Ver estado
python manage.py status
```

### Método 4: Manual
```bash
# Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# Ejecutar aplicación
python app.py
```

## 🛠️ Problemas Comunes y Soluciones

### ❌ Problema: "Import 'flask' could not be resolved"
**Solución:**
```bash
pip install flask werkzeug pdfkit num2words markupsafe
```

### ❌ Problema: "No Python at 'C:\Users\CCN 303\...'"
**Solución:** Recrear entorno virtual
```bash
Remove-Item .venv -Recurse -Force
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### ❌ Problema: Puerto 5000 ocupado
**Solución:** Detener procesos Flask
```bash
python manage.py stop
# o
Get-Process python | Stop-Process -Force
```

### ❌ Problema: Procesos Flask colgados
**Solución:**
```bash
# Listar procesos Python
Get-Process python

# Detener procesos específicos
Stop-Process -Id [PID] -Force

# O usar el manager
python manage.py stop
```

### ❌ Problema: Variables de entorno no cargadas
**Solución:** Verificar archivo `.env`
```bash
# El archivo .env debe contener:
FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
```

### ❌ Problema: Base de datos no funciona
**Solución:**
```bash
# Eliminar base de datos existente
Remove-Item database\db.sqlite3 -Force

# Reiniciar aplicación para recrear
python app.py
```

## 🔧 Comandos Útiles de Diagnóstico

### Verificar entorno virtual
```bash
where python
python --version
pip list
```

### Verificar importaciones
```bash
python -c "import flask; print('Flask OK')"
python -c "import app; print('App OK')"
```

### Verificar puertos
```bash
netstat -an | findstr :5000
```

### Limpiar cache Python
```bash
Remove-Item __pycache__ -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .pytest_cache -Recurse -Force -ErrorAction SilentlyContinue
```

## 📱 URLs de la Aplicación

Una vez iniciada, la aplicación estará disponible en:
- **Local:** http://127.0.0.1:5000
- **Red local:** http://192.168.100.254:5000

## ⚠️ Warnings Normales (No son errores)

```
WARNING: This is a development server. Do not use it in a production deployment.
```
Este warning es normal en desarrollo. Para producción usarías un servidor WSGI como Gunicorn.

## 🔄 Reinicio Completo

Si tienes problemas persistentes:
```bash
# 1. Detener todos los procesos
python manage.py stop

# 2. Limpiar cache
Remove-Item __pycache__ -Recurse -Force -ErrorAction SilentlyContinue

# 3. Reiniciar
python manage.py start
```