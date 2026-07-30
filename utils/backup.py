import os
import shutil
import sqlite3
from datetime import datetime

def get_backup_dir():
    folder = os.environ.get('BACKUP_DIR', 'respaldo')
    if not os.path.isabs(folder):
        folder = os.path.join(os.getcwd(), folder)
    os.makedirs(folder, exist_ok=True)
    return folder

def get_target_db_path():
    if os.environ.get('TESTING_DB'):
        return os.path.abspath(os.environ.get('TESTING_DB'))
    return os.path.abspath(os.path.join(os.getcwd(), 'database', 'db.sqlite3'))

def crear_backup(prefix="backup"):
    """
    Crea una copia de seguridad en caliente de la base de datos usando sqlite3.backup().
    """
    db_path = get_target_db_path()
    backup_dir = get_backup_dir()

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Base de datos no encontrada en: {db_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.sqlite3"
    dest_path = os.path.join(backup_dir, filename)

    source_conn = sqlite3.connect(db_path)
    dest_conn = sqlite3.connect(dest_path)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    return filename, dest_path

def listar_backups():
    """
    Lista todos los archivos .sqlite3 en la carpeta de respaldos ordenados del más reciente al más antiguo.
    """
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []

    backups = []
    for fname in os.listdir(backup_dir):
        if fname.endswith('.sqlite3'):
            fpath = os.path.join(backup_dir, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                backups.append({
                    'filename': fname,
                    'size_bytes': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'created_at': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'timestamp': stat.st_mtime
                })

    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return backups

def eliminar_backup(filename):
    """
    Elimina un archivo de respaldo de forma segura.
    """
    safe_filename = os.path.basename(filename)
    backup_dir = get_backup_dir()
    fpath = os.path.join(backup_dir, safe_filename)

    if not os.path.exists(fpath):
        raise FileNotFoundError(f"El archivo de respaldo {safe_filename} no existe.")

    os.remove(fpath)
    return True

def restaurar_backup(filename):
    """
    Restaura la base de datos a partir de un respaldo, generando un respaldo automático previo.
    """
    safe_filename = os.path.basename(filename)
    backup_dir = get_backup_dir()
    backup_src = os.path.join(backup_dir, safe_filename)

    if not os.path.exists(backup_src):
        raise FileNotFoundError(f"El archivo de respaldo {safe_filename} no existe.")

    db_target = get_target_db_path()

    # 1. Crear auto-respaldo preventivo antes de restaurar
    crear_backup(prefix="auto_pre_restore")

    # 2. Copiar backup al archivo de base de datos destino usando API de backup
    src_conn = sqlite3.connect(backup_src)
    tgt_conn = sqlite3.connect(db_target)
    try:
        src_conn.backup(tgt_conn)
    finally:
        tgt_conn.close()
        src_conn.close()

    return True
