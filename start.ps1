# Script para iniciar la aplicación Flask en PowerShell

Write-Host "🚀 Iniciando aplicación Flask..." -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Blue

# Activar entorno virtual
Write-Host "📦 Activando entorno virtual..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Configurar variables de entorno
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"

# Mostrar información
Write-Host "✅ Entorno virtual activado" -ForegroundColor Green
Write-Host "🌐 La aplicación estará disponible en:" -ForegroundColor Cyan
Write-Host "   - http://127.0.0.1:5000" -ForegroundColor White
Write-Host "   - http://localhost:5000" -ForegroundColor White
Write-Host "=================================" -ForegroundColor Blue
Write-Host "💡 Presiona Ctrl+C para detener la aplicación" -ForegroundColor Magenta
Write-Host ""

# Iniciar aplicación
try {
    python app.py
}
catch {
    Write-Host "❌ Error al iniciar la aplicación: $_" -ForegroundColor Red
}
finally {
    Write-Host "🛑 Aplicación detenida" -ForegroundColor Yellow
}