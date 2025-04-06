# executor.py
import atexit
import queue
import re  # Importar el módulo re
import subprocess
import threading
import time

import logging_manager


class MongoExecutor:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.lock = threading.Lock()
        self.prompt_pattern = "\n> " # Default prompt pattern, might change based on DB
        self._start_process()
        atexit.register(self._stop_process) # Ensure cleanup on exit

    def _start_process(self):
        if self.process and self.process.poll() is None:
            # Process already running
            return

        logging_manager.log_debug("Executor", "Starting new mongosh process...")
        try:
            # Start mongosh, connect pipes for stdin, stdout, stderr
            self.process = subprocess.Popen(
                ["mongosh", "--quiet"], # --quiet suppresses connection messages
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1, # Line buffered
                universal_newlines=True # Ensures text mode works correctly
            )

            # Start threads to read stdout and stderr without blocking
            self.stdout_thread = threading.Thread(target=self._read_output, args=(self.process.stdout,), daemon=True)
            self.stderr_thread = threading.Thread(target=self._read_output, args=(self.process.stderr,), daemon=True)
            self.stdout_thread.start()
            self.stderr_thread.start()

            # Wait briefly for the process to initialize and potentially show the first prompt
            time.sleep(0.5)
            # Consume any initial output/prompt
            self._read_until_prompt(timeout=2)
            logging_manager.log_debug("Executor", "mongosh process started successfully.")

        except Exception as e:
            logging_manager.log_debug("Executor Error", f"Failed to start mongosh process: {e}")
            self.process = None
            raise RuntimeError(f"Failed to start mongosh process: {e}")

    def _stop_process(self):
        if self.process and self.process.poll() is None:
            logging_manager.log_debug("Executor", "Stopping mongosh process...")
            try:
                self.process.terminate() # Try graceful termination
                self.process.wait(timeout=5) # Wait for termination
            except subprocess.TimeoutExpired:
                logging_manager.log_debug("Executor", "mongosh process did not terminate gracefully, killing.")
                self.process.kill() # Force kill if terminate fails
            except Exception as e:
                 logging_manager.log_debug("Executor Error", f"Error stopping mongosh: {e}")
            self.process = None
            logging_manager.log_debug("Executor", "mongosh process stopped.")

    def _read_output(self, pipe):
        """Reads lines from a pipe and puts them into the queue."""
        try:
            while True:
                line = pipe.readline()
                if not line: # Pipe closed
                    break
                self.output_queue.put(line)
        except Exception as e:
            # Handle exceptions during read, e.g., if pipe closes unexpectedly
            logging_manager.log_debug("Executor Read Error", f"Error reading pipe: {e}")
        finally:
             # Signal that reading from this pipe is done (optional, depends on logic)
             self.output_queue.put(None) # Use None as a sentinel value if needed

    def _read_until_prompt(self, timeout=5): # Reducido timeout general a 5s
        """
        Reads from the queue until a prompt pattern (like 'db_name> ') is detected
        at the end of a line or timeout occurs. Uses regex for robust detection.
        """
        output_lines = []
        start_time = time.time()
        prompt_found = False
        # Regex para detectar prompts como 'test> ', 'admin> ', '> ', etc., al final de la línea
        # Permite nombres de db alfanuméricos y guiones bajos.
        prompt_re = re.compile(r"^(?:[\w-]+>|>) $") # Busca el patrón al inicio de la línea y que sea toda la línea

        # Bucle principal para leer la salida
        buffer = "" # Acumular líneas parciales si es necesario
        last_line_read = ""

        while time.time() - start_time < timeout:
            try:
                # Usar timeout pequeño para no bloquear mucho, pero permitir que lleguen datos
                line = self.output_queue.get(timeout=0.2)
                if line is None: continue # Sentinel

                # Limpiar la línea de posibles caracteres de control ANSI (aunque --quiet debería ayudar)
                # line_cleaned = re.sub(r'\x1b\[[0-9;]*[mK]', '', line)
                line_cleaned = line # Asumimos que --quiet elimina la mayoría

                output_lines.append(line_cleaned)
                last_line_read = line_cleaned.rstrip() # Guardar la última línea sin salto de línea final

                # Usar regex para detectar el prompt al final de la línea
                # logging_manager.log_debug("Checking line for prompt", f"'{last_line_read}' against regex") # Debug extra
                if prompt_re.match(last_line_read):
                    logging_manager.log_debug("Executor", f"Prompt detected: '{last_line_read}'")
                    prompt_found = True
                    # Eliminar la línea del prompt de la salida final
                    output_lines.pop()
                    break # Salir del bucle while

            except queue.Empty:
                # Si la cola está vacía, puede que el comando haya terminado
                # pero aún no hemos detectado el prompt. Si ha pasado un tiempo prudencial
                # sin nueva salida, podríamos asumir que terminó (más arriesgado).
                # Por ahora, simplemente continuamos esperando hasta el timeout general.
                if output_lines: # Si ya tenemos algo de salida, esperamos un poco más
                     pass # Continuar esperando
                else: # Si no hay salida y la cola está vacía, esperamos
                     pass
            except Exception as e:
                 logging_manager.log_debug("Executor Queue Error", f"Error getting from queue: {e}")
                 break # Salir en caso de error

        if not prompt_found and time.time() - start_time >= timeout:
             logging_manager.log_debug("Executor Timeout", f"Timeout ({timeout}s) waiting for prompt. Last line read: '{last_line_read}'")
             # Devolver lo que se haya podido leer

        full_output = "".join(output_lines).strip()
        # logging_manager.log_debug("Raw output before return", full_output) # Debug

        # Ya no necesitamos la comprobación de ';' porque la detección de prompt debería ser mejor
        # if full_output.endswith(';'): ...

        return full_output


    def execute_command(self, command: str) -> str:
        """Executes a command in the persistent mongosh process."""
        with self.lock: # Ensure only one command executes at a time
            if not self.process or self.process.poll() is not None:
                logging_manager.log_debug("Executor", "Process not running, attempting restart.")
                try:
                    self._start_process()
                except RuntimeError as e:
                    return f"Error: Could not start or restart mongosh process. {e}"

            if not self.process:
                 return "Error: mongosh process is not available."

            logging_manager.log_debug("Executor Input", command)
            try:
                # Send command, ensuring newline
                self.process.stdin.write(command + '\n')
                self.process.stdin.flush()

                # Read output until the next prompt appears
                output = self._read_until_prompt(timeout=1) # Increased timeout for potentially long commands
                logging_manager.log_debug("Executor Output", output)

                # Basic check for common errors in stderr output (might need refinement)
                if "SyntaxError:" in output or "ReferenceError:" in output or "MongoServerError:" in output:
                     logging_manager.log_debug("Executor Error Detected", output)
                     # Consider how to report errors vs normal output

                # Update prompt pattern based on output if needed (e.g., after 'use db')
                lines = output.splitlines()
                if lines:
                    last_line = lines[-1]
                    if last_line.endswith('>'):
                         # Simplistic update, assumes last line contains the new prompt
                         # Might need regex `r"(\w+)> $"`
                         potential_prompt = last_line.strip()
                         if potential_prompt != self.prompt_pattern.strip():
                              self.prompt_pattern = potential_prompt + " " # Add space back
                              logging_manager.log_debug("Executor", f"Prompt updated to: '{self.prompt_pattern}'")


                return output

            except BrokenPipeError:
                 logging_manager.log_debug("Executor Error", "Broken pipe: mongosh process likely terminated.")
                 self.process = None # Mark process as dead
                 return "Error: mongosh process terminated unexpectedly."
            except Exception as e:
                logging_manager.log_debug("Executor Exception", f"Error during command execution: {e}")
                # Attempt to stop/restart the process on error?
                # self._stop_process()
                return f"Error executing command: {e}"

# Global instance
_mongo_executor_instance = None

def get_executor_instance():
    """Gets the singleton instance of MongoExecutor."""
    global _mongo_executor_instance
    if _mongo_executor_instance is None:
        _mongo_executor_instance = MongoExecutor()
    return _mongo_executor_instance

def execute_mongo_command(command: str) -> str:
    """
    Public function to execute a command using the singleton executor instance.
    """
    executor_instance = get_executor_instance()
    return executor_instance.execute_command(command)

# Example of how to ensure cleanup (already handled by atexit)
# def cleanup():
#     if _mongo_executor_instance:
#         _mongo_executor_instance._stop_process()
# atexit.register(cleanup)
