# Script para ejecutar la aplicación Flask con la virtualenv activada
param(
    [switch]$Debug,
    [string]$Host = "127.0.0.1",
    [int]$Port = 5000
)

# Verificar si estamos en la carpeta correcta (debe existir app.py)
if (-not (Test-Path "app.py")) {
    Write-Host "Error: No se encuentra app.py. Ejecuta este script desde la raíz del proyecto." -ForegroundColor Red
    exit 1
}

# Función para activar la virtualenv
function Activate-Venv {
    if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
        Write-Host "Error: No se encuentra la virtualenv. Creándola..." -ForegroundColor Yellow
        try {
            py -3 -m venv .venv
            if (-not $?) { throw "Error al crear virtualenv" }
        }
        catch {
            Write-Host "Error al crear la virtualenv. Asegúrate de tener Python instalado." -ForegroundColor Red
            exit 1
        }
    }

    try {
        # Intentar activar la virtualenv
        . ".venv\Scripts\Activate.ps1"
    }
    catch {
        Write-Host "No se pudo activar la virtualenv. Intentando ajustar la política de ejecución..." -ForegroundColor Yellow
        try {
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
            . ".venv\Scripts\Activate.ps1"
        }
        catch {
            Write-Host "Error al activar la virtualenv. Ejecuta como administrador: Set-ExecutionPolicy RemoteSigned" -ForegroundColor Red
            exit 1
        }
    }
}

# Función para instalar dependencias si faltan
function Install-Requirements {
    if (Test-Path "requirements.txt") {
        Write-Host "Verificando/instalando dependencias..." -ForegroundColor Cyan
        python -m pip install -r requirements.txt
        if (-not $?) {
            Write-Host "Error al instalar dependencias." -ForegroundColor Red
            exit 1
        }
    }
}

# Activar virtualenv e instalar dependencias
Activate-Venv
Install-Requirements

# Configurar variables de entorno para Flask
$env:FLASK_APP = "app.py"
if ($Debug) {
    $env:FLASK_ENV = "development"
    $env:FLASK_DEBUG = "1"
    Write-Host "Modo DEBUG activado" -ForegroundColor Yellow
}
else {
    $env:FLASK_ENV = "production"
    $env:FLASK_DEBUG = "0"
}

# Ejecutar Flask
Write-Host "Iniciando servidor Flask en http://$($Host):$($Port)" -ForegroundColor Green
Write-Host "Presiona Ctrl+C para detener el servidor" -ForegroundColor Cyan

try {
    python -m flask run --host=$Host --port=$Port
}
catch {
    Write-Host "`nServidor detenido" -ForegroundColor Yellow
}
finally {
    # Limpiar variables de entorno
    Remove-Item Env:\FLASK_APP -ErrorAction SilentlyContinue
    Remove-Item Env:\FLASK_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:\FLASK_DEBUG -ErrorAction SilentlyContinue
}