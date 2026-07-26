import re
import os

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Import the db wrapper
    if 'from db_wrapper import get_db_connection' not in content:
        content = content.replace('import sqlite3\n', 'import sqlite3\nfrom db_wrapper import get_db_connection\n')

    # Replace sqlite3.connect calls
    content = re.sub(r"sqlite3\.connect\('database/db\.sqlite3'(?:,\s*timeout=30)?\)", "get_db_connection()", content)

    # Patch lastrowid by adding RETURNING id to the preceding INSERT
    # For categorias
    content = re.sub(
        r'(INSERT INTO categorias.*?VALUES\s*\(\?,\s*\?,\s*1\))("|\')',
        r'\1 RETURNING id\2',
        content,
        flags=re.DOTALL
    )
    # For cotizaciones
    content = re.sub(
        r'(INSERT INTO cotizaciones.*?VALUES\s*\(\?,\s*\?,\s*\?,\s*\?,\s*\?,\s*\?\))("|\')',
        r'\1 RETURNING id\2',
        content,
        flags=re.DOTALL
    )
    # For clientes (admin)
    content = re.sub(
        r'(INSERT INTO clientes.*?VALUES\s*\(\?,\s*\?,\s*\?,\s*\?,\s*\?\))("|\')',
        r'\1 RETURNING id\2',
        content,
        flags=re.DOTALL
    )
    # For importaciones_pdf
    content = re.sub(
        r'(INSERT INTO importaciones_pdf.*?VALUES\s*\(\?,\s*\?,\s*\?\))("|\')',
        r'\1 RETURNING id\2',
        content,
        flags=re.DOTALL
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    base_dir = r"f:\Proyectos\ProyectoCotizacion\ProyectoCotizacion"
    patch_file(os.path.join(base_dir, 'app.py'))
    patch_file(os.path.join(base_dir, 'models.py'))
    print("Patching complete.")
