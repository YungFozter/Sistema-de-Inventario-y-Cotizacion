#!/usr/bin/env python3
"""
Script de gestión para la aplicación Flask
Proporciona comandos para iniciar, detener y reiniciar la aplicación de manera limpia
"""

import os
import sys
import subprocess
import signal
import psutil
import time
from pathlib import Path

class FlaskManager:
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.venv_python = self.project_dir / ".venv" / "Scripts" / "python.exe"
        self.app_file = self.project_dir / "app.py"
        
    def activate_venv(self):
        """Activa el entorno virtual"""
        if not self.venv_python.exists():
            print("❌ Entorno virtual no encontrado. Ejecuta: python -m venv .venv")
            return False
        return True
        
    def find_flask_processes(self):
        """Encuentra procesos Flask ejecutándose"""
        flask_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'app.py' in cmdline or 'flask' in cmdline.lower():
                        flask_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return flask_processes
        
    def stop_flask(self):
        """Detiene todos los procesos Flask"""
        processes = self.find_flask_processes()
        if not processes:
            print("ℹ️  No se encontraron procesos Flask ejecutándose")
            return True
            
        print(f"🛑 Deteniendo {len(processes)} proceso(s) Flask...")
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                print(f"✅ Proceso {proc.pid} detenido")
            except psutil.TimeoutExpired:
                proc.kill()
                print(f"🔥 Proceso {proc.pid} terminado forzadamente")
            except Exception as e:
                print(f"❌ Error deteniendo proceso {proc.pid}: {e}")
        return True
        
    def start_flask(self):
        """Inicia la aplicación Flask"""
        if not self.activate_venv():
            return False
            
        # Detener procesos existentes
        self.stop_flask()
        time.sleep(1)
        
        print("🚀 Iniciando aplicación Flask...")
        print("=" * 50)
        print("📍 Aplicación disponible en:")
        print("   • http://127.0.0.1:5000")
        print("   • http://localhost:5000")
        print("=" * 50)
        print("💡 Presiona Ctrl+C para detener")
        print()
        
        try:
            # Configurar variables de entorno
            env = os.environ.copy()
            env.update({
                'FLASK_APP': 'app.py',
                'FLASK_ENV': 'development',
                'FLASK_DEBUG': '1'
            })
            
            # Ejecutar la aplicación
            subprocess.run([str(self.venv_python), str(self.app_file)], 
                         cwd=str(self.project_dir), env=env, check=True)
        except KeyboardInterrupt:
            print("\n🛑 Aplicación detenida por el usuario")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error ejecutando la aplicación: {e}")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
        finally:
            self.stop_flask()
            
    def restart_flask(self):
        """Reinicia la aplicación Flask"""
        print("🔄 Reiniciando aplicación Flask...")
        self.stop_flask()
        time.sleep(2)
        self.start_flask()
        
    def status(self):
        """Muestra el estado de la aplicación"""
        processes = self.find_flask_processes()
        if processes:
            print(f"✅ Flask ejecutándose ({len(processes)} proceso(s))")
            for proc in processes:
                print(f"   • PID: {proc.pid}")
        else:
            print("❌ Flask no está ejecutándose")

def main():
    manager = FlaskManager()
    
    if len(sys.argv) < 2:
        print("Uso: python manage.py [start|stop|restart|status]")
        return
        
    command = sys.argv[1].lower()
    
    if command == 'start':
        manager.start_flask()
    elif command == 'stop':
        manager.stop_flask()
    elif command == 'restart':
        manager.restart_flask()
    elif command == 'status':
        manager.status()
    else:
        print("Comando no válido. Use: start, stop, restart, o status")

if __name__ == "__main__":
    main()