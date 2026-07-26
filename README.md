# ProyectoCotizacion — Notas sobre la virtualenv

Resumen rápido

- He detectado que la carpeta `.venv` existe en el proyecto, pero varios ficheros dentro (`pyvenv.cfg`, shebangs y scripts de activación) contienen rutas absolutas a `C:\Users\Usuario\ProyectoCotizacion\.venv`.
- Eso normalmente ocurre cuando la venv se creó en otra ubicación (por ejemplo en C:) y luego el repositorio se movió a otra unidad (`E:`). Como resultado la venv puede estar rota y la activación o ejecutables pueden no funcionar.

Opciones recomendadas (seguras):

1) Recrear la virtualenv (recomendado)

- Abre PowerShell en la carpeta raíz del proyecto (`E:\ProyectoCotizacion`).
- Ejecuta (usa la versión de Python que quieras):

```powershell
# Elimina la venv existente (si estás de acuerdo)
Remove-Item -Recurse -Force .venv

# Crea una nueva venv usando el Python por defecto del PATH
python -m venv .venv

# Activa (PowerShell). Si falla por políticas de ejecución, ver más abajo.
.\.venv\Scripts\Activate.ps1

# Luego instala dependencias
.\.venv\Scripts\pip.exe install -r requirements.txt
```

2) Alternativa: arreglar rutas internas (no recomendable)

- Es posible editar `pyvenv.cfg` y algunos scripts para apuntar a la nueva ruta, pero es frágil. Por simplicidad y seguridad es mejor recrear la venv.

Políticas de ejecución (PowerShell)

- Si PowerShell rechaza ejecutar `Activate.ps1` por la política de ejecución, ejecuta (solo una vez por usuario):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

- No es necesario hacerlo como administrador.

Helper: `activate_venv.ps1`

- He incluido un script `activate_venv.ps1` que intenta ajustar la política de ejecución en el usuario y luego activa la venv (dot-source). Úsalo desde la raíz del proyecto si prefieres un comando único.

Comprobaciones rápidas

- Tras recrear la venv, verifica:
  - `python --version` dentro de la venv
  - `pip list` para ver paquetes instalados
  - `python -c "import flask, pdfkit"` (u otros imports que use tu app) para detectar paquetes faltantes

Notas finales

- Si quieres que recree la venv aquí (dentro del entorno de desarrollo remoto), puedo generar un script PowerShell adicional o ejecutar comandos, pero normalmente deberías ejecutarlo en tu máquina local (E:).
- Dime si quieres que cree un commit con los archivos de ayuda (`README.md` y `activate_venv.ps1`) o si prefieres que además recree la venv desde aquí.
