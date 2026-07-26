@echo off
REM Script para iniciar la aplicación Flask de manera limpia

echo Activando entorno virtual...
call .venv\Scripts\activate.bat

echo Configurando variables de entorno...
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_DEBUG=1

echo Iniciando aplicación Flask...
echo =====================================
echo Aplicación disponible en:
echo - http://127.0.0.1:5000
echo - http://localhost:5000
echo =====================================
echo Presiona Ctrl+C para detener
echo.

python app.py

pause