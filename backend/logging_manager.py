# logging_manager.py
import os
from datetime import datetime

LOG_FILE = "mongo_agent.log" # Revertido a .log

def _write_log(level: str, message: str):
    """Función interna para escribir en el log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] # Añadir milisegundos
    log_line = f"{timestamp} - {level} - {message}\n"
    try:
        # Usar 'a+' para crear el archivo si no existe
        with open(LOG_FILE, "a+", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"Error al escribir en el log: {e}")

def add_log(entry: str):
    """Agrega una entrada de conversación (INFO) al archivo de log."""
    _write_log("INFO", entry)

def log_debug(label: str, data: str):
    """Agrega una entrada de depuración (DEBUG) al archivo de log."""
    # Formatear datos multilínea para mejor legibilidad
    formatted_data = data.replace('\n', '\n' + ' ' * (len(label) + 12)) # Indentar líneas siguientes
    _write_log("DEBUG", f"[{label}]: {formatted_data}")


def get_log() -> str:
    """Devuelve el log completo como una cadena de texto desde el archivo."""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return f.read()
        else:
            return "El archivo de log aún no existe."
    except Exception as e:
        print(f"Error al leer el log: {e}")
        return f"Error al leer el log: {e}"

def print_log():
    """Indica la ubicación del archivo de log."""
    print(f"El log completo se encuentra en: {os.path.abspath(LOG_FILE)}")

# Limpiar el log al inicio de cada ejecución.
try:
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
        print(f"Log anterior ({LOG_FILE}) eliminado.") # Mensaje informativo
except Exception as e:
    print(f"Advertencia: No se pudo limpiar el log anterior ({LOG_FILE}): {e}")
