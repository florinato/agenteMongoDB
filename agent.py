import os
import subprocess

import google.generativeai as genai
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# Load environment variables
MONGODB_URI = os.environ.get("MONGODB_URI")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable not set")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

# Initialize Gemini LLM
def initialize_llm(model_name="gemini-1.5-pro-latest"):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name)
    return model

# Generate mongosh command
def generate_mongo_command(natural_language_input, llm):
    prompt = f"""
    Eres un experto en MongoDB. Convierte la siguiente instrucción en lenguaje natural en un comando mongosh válido y ejecutable.
    {natural_language_input}
    Si la instrucción es explorar la base de datos, enumera las bases de datos y las colecciones.
    Si encuentras alguna dificultad para realizar la operación, explica las dificultades al usuario como comentarios en el script.
    El script debe ser una sola línea de código javascript ejecutable directamente por mongosh.
    NO incluyas explicaciones, comentarios (excepto el inicial '// javascript'), ni formato markdown como ```javascript.
    SOLO devuelve la línea de código javascript.
    Ejemplo de salida esperada para 'listar bases de datos': // javascript\ndb.adminCommand('listDatabases')

    {natural_language_input}
    """
    response = llm.generate_content(prompt)
    raw_script = response.text.strip()

    # Limpieza más robusta de la respuesta del LLM
    script_lines = raw_script.splitlines()
    js_code = ""
    for line in script_lines:
        cleaned_line = line.strip()
        # Ignorar líneas vacías o comentarios de explicación del LLM
        if not cleaned_line or cleaned_line.startswith("// Eres") or cleaned_line.startswith("// Si"):
             continue
        # Eliminar marcadores de markdown
        if cleaned_line.startswith("```javascript"):
            cleaned_line = cleaned_line[len("```javascript"):].strip()
        if cleaned_line.startswith("// javascript"): # Quitar el marcador si el LLM lo añade incorrectamente aquí
             cleaned_line = cleaned_line[len("// javascript"):].strip()
        if cleaned_line.endswith("```"):
            cleaned_line = cleaned_line[:-len("```")].strip()
        # Tomar la primera línea que parezca código válido
        if cleaned_line:
             js_code = cleaned_line
             break # Asumimos que la primera línea válida es el comando

    # Si no se encontró código válido, intentar un fallback o registrar error
    if not js_code:
        print(f"Advertencia: No se pudo extraer código JS válido de la respuesta del LLM: {raw_script}")
        js_code = "'Error: Comando no generado'" # Devolver una cadena de error JS

    # Devolver directamente el código JS para --eval
    return js_code


import re
# Execute mongosh command
import shlex


def execute_mongo_command(command_string):
    # Limpiar el comando de posibles caracteres problemáticos para --eval
    # Quitar comentarios JS
    command_string = re.sub(r'//.*', '', command_string).strip()
    # Escapar comillas simples si se usan comillas simples para envolver en --eval
    # O usar comillas dobles para envolver si el comando no las contiene
    if "'" in command_string and '"' not in command_string:
        eval_wrapper = '"'
    else:
        eval_wrapper = "'"
        command_string = command_string.replace("'", "\\'") # Escapar comillas simples internas

    # Construir el comando final para mongosh --eval
    full_command = f"mongosh --quiet --eval {eval_wrapper}{command_string}{eval_wrapper}"

    try:
        print(f"Ejecutando comando: {full_command}") # Log para depuración
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True,
            check=True # Raise exception on non-zero exit code
        )
        return result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr

# Label utterance
def label_utterance(role, content):
    return {"role": role, "content": content}

import json


def analyze_mongo_output(output, error, llm):
    prompt = f"""
    Analiza la siguiente salida y error de un comando mongosh.
    Salida: ```{output}```
    Error: ```{error}```

    Determina si el comando fue exitoso.
    Si fue exitoso, extrae los datos clave de la salida.
    Si falló, extrae el mensaje de error principal.

    Responde SÓLO con un objeto JSON con la siguiente estructura:
    {{
      "exito": boolean,
      "datos": string_o_null, // Datos clave si exito es true, null si no
      "mensaje_error": string_o_null // Mensaje de error si exito es false, null si no
    }}
    """
    try:
        response = llm.generate_content(prompt)
        # Intenta limpiar la respuesta del LLM para obtener solo el JSON
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        analysis = json.loads(json_str)
        # Validar estructura básica
        if not isinstance(analysis, dict) or "exito" not in analysis:
             raise ValueError("Respuesta JSON inválida del LLM")
        return analysis
    except (json.JSONDecodeError, ValueError, Exception) as e:
        # Fallback en caso de error del LLM o JSON inválido
        print(f"Error al analizar la salida del LLM: {e}")
        print(f"Respuesta LLM original: {response.text if 'response' in locals() else 'No response'}")
        return {
            "exito": False if error else True, # Asume éxito si no hay error explícito
            "datos": output if not error else None,
            "mensaje_error": error if error else "Error al procesar la respuesta del análisis."
        }

def generate_response(analysis_result, llm):
    prompt = f"""
    Basado en el siguiente análisis de la ejecución de un comando mongosh:
    {json.dumps(analysis_result, indent=2)}

    Genera una respuesta concisa y clara para el usuario final en español.
    Si exito es true, resume los datos clave de forma amigable.
    Si exito es false, informa del error explicando brevemente la causa basada en el 'mensaje_error'.
    """
    try:
        response = llm.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error al generar la respuesta: {e}")
        # Fallback response
        if analysis_result.get("exito"):
            return f"Comando ejecutado. Datos: {analysis_result.get('datos', 'N/A')}"
        else:
            return f"Error al ejecutar comando: {analysis_result.get('mensaje_error', 'Desconocido')}"

# Main agent loop (Phase 2)
def main():
    llm = initialize_llm()
    while True:
        natural_language_input = input("Enter your instruction: ")
        user_utterance = label_utterance("Usuario", natural_language_input)

        mongo_command = generate_mongo_command(natural_language_input, llm)
        agent_generating_utterance = label_utterance("Agente - Generando Comando", mongo_command)

        stdout, stderr = execute_mongo_command(mongo_command)
        mongodb_utterance = label_utterance("MongoDB", stdout + "\\n" + stderr)

        analysis_result = analyze_mongo_output(stdout, stderr, llm)
        # Guardamos la salida cruda de MongoDB para referencia, pero generamos una respuesta más amigable
        mongodb_utterance = label_utterance("MongoDB - Salida Cruda", stdout + "\\n" + stderr if stdout or stderr else "Sin salida")

        final_response = generate_response(analysis_result, llm)
        agent_response_utterance = label_utterance("Agente - Respuesta", final_response)

        # Imprime el historial de diálogo completo
        print(json.dumps([user_utterance, agent_generating_utterance, mongodb_utterance, agent_response_utterance], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
