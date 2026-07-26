<#
Helper para activar la virtualenv del proyecto en PowerShell.
Uso: Ejecuta este script desde la raíz del proyecto: `.
activate_venv.ps1`

Qué hace:
- Comprueba si `.venv` existe.
- Intenta ajustar ExecutionPolicy para el CurrentUser (solo si es necesario).
- Dot-sourcea el `Activate.ps1` dentro de `.venv\Scripts`.
#>

$venvPath = Join-Path (Get-Location) '.venv\Scripts\Activate.ps1'
if (-not (Test-Path $venvPath)) {
    Write-Host "No se encontró .venv/Activate.ps1 en: $venvPath" -ForegroundColor Red
    Write-Host "Si la venv fue movida entre unidades es recomendable recrearla: `python -m venv .venv`" -ForegroundColor Yellow
    exit 1
}

# Check execution policy
$policy = Get-ExecutionPolicy -Scope CurrentUser -ErrorAction SilentlyContinue
if ($policy -eq 'Restricted') {
    Write-Host "La política actual es 'Restricted'. Cambiaré a RemoteSigned para este usuario..." -ForegroundColor Yellow
    try {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction Stop
    }
    catch {
        Write-Host "No se pudo cambiar ExecutionPolicy: $_" -ForegroundColor Red
        Write-Host "Ejecuta manualmente: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
        exit 1
    }
}

# Dot-source the activate script to keep session variables
try {
    Write-Host "Activando la virtualenv desde: $venvPath" -ForegroundColor Green
    . $venvPath
    Write-Host "Activado. Comprueba python --version y pip list." -ForegroundColor Green
}
catch {
    Write-Host "Error al activar la venv: $_" -ForegroundColor Red
    exit 1
}
