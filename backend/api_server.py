import os  # Added for path joining
import uuid
from typing import Optional  # Add Optional for the new fields

# Local imports
import communication
import executor
import logging_manager
import security
import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse  # Added for serving index.html
from fastapi.staticfiles import StaticFiles  # Added for static files
# Langchain imports (adjust if needed based on actual usage in main.py)
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts.prompt import PromptTemplate
from model_integration import GeminiLLM
from pydantic import BaseModel

# --- FastAPI App Initialization ---
app = FastAPI(
    title="MongoDB Agent API",
    description="API wrapper for the Langchain MongoDB Agent",
    version="0.1.0",
)

# --- Static Files Mounting ---
# Serve static files from the frontend directory
# The path "/static" means URLs like http://.../static/script.js will work
# We'll also add a root route for index.html separately
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# --- In-Memory State Storage ---
# Stores active ConversationChain instances keyed by session_id
conversations = {}
# pending_confirmations dictionary removed as confirmation is now inline

# --- Pydantic Models (for request/response validation) ---
class UserQuery(BaseModel):
    user_query: Optional[str] = None # Make original query optional
    confirmed_command: Optional[str] = None # Field for the command confirmed by the UI

# Confirmation model removed

class SessionResponse(BaseModel):
    session_id: str

class ChatResponse(BaseModel):
    status: str # e.g., "completed", "confirmation_required", "cancelled", "error"
    response: Optional[str] = None # Final answer or error/info message
    command_to_confirm: Optional[str] = None # The dangerous command needing UI confirmation

# --- Langchain Prompt Template (Copied from main.py) ---
# TODO: Consider moving this to a separate config file or module
TEMPLATE = """Eres el agente Gemini-2.0-flash-001, un asistente experto en MongoDB. Interactúas con MongoDB usando la función `execute_mongo_command`.

**Características Clave:**

1.  **Mantenimiento de Contexto:** ¡Importante! El sistema **recuerda** la base de datos seleccionada con `use` entre comandos. Puedes realizar operaciones en varios pasos enviando comandos individuales secuencialmente. Analiza el 'Historial de la conversación' para saber en qué base de datos estás.
2.  **Comandos Soportados:** Puedes usar la mayoría de comandos estándar de `mongosh`:
    *   Selección de BD: `use <nombre_db>`
    *   Información: `db.getName()`, `show dbs`, `show collections`, `db.getCollectionNames()`
    *   Operaciones CRUD: `db.<col>.insertOne({{ ... }})`, `db.<col>.insertMany([{{...}}, {{...}}])`, `db.<col>.find({{ ... }})`, `db.<col>.updateOne({{ ... }}, {{ ... }})`, `db.<col>.deleteOne({{ ... }})`, `db.<col>.countDocuments({{ ... }})` (Nota: Llaves para JSON deben escaparse como `{{` y `}}`).
    *   Otros: `print('...')`, `db.runCommand({{ ... }})`
3.  **Ejecución Secuencial:** Para tareas que requieren múltiples pasos (ej. cambiar de DB y luego buscar), envía **un comando por cada respuesta**. No intentes encadenar comandos con punto y coma (`;`) en una sola respuesta.

**Flujo de Trabajo Autónomo:**

1.  Recibirás una 'Entrada del usuario' inicial. Analízala junto con el 'Historial de la conversación'.
2.  Determina el primer comando `mongosh` necesario para la tarea.
3.  Genera tu respuesta como `consulta mongo: <comando>`.
4.  **IMPORTANTE:** El sistema ejecutará tu comando y te devolverá **inmediatamente** el resultado como una nueva entrada en el historial con la etiqueta `respuesta mongo: <resultado>`.
5.  **ITERACIÓN:** Analiza esta `respuesta mongo:` y el estado actual de la tarea.
    *   Si se necesitan más pasos (ej. ejecutar la consulta principal después de un `use`, o realizar otra acción), genera la siguiente `consulta mongo: <siguiente_comando>`. El sistema volverá a ejecutarlo y te dará el resultado.
    *   Repite este proceso, generando `consulta mongo:` para cada paso necesario.
6.  **FINALIZACIÓN:** Cuando hayas completado **todos** los pasos necesarios para satisfacer la petición original del usuario, genera tu respuesta final como `respuesta usuario: <mensaje_final_al_usuario>`. Esto detendrá el ciclo de iteración para esa petición.
7.  **SEGURIDAD:** Si necesitas ejecutar un comando peligroso (ej. `dropDatabase`, `drop`, `delete`), **antes** de generar la `consulta mongo:` para ese comando, genera `respuesta usuario: ¿Estás seguro de que quieres ejecutar [comando peligroso]?`. El sistema gestionará la confirmación del usuario; si es positiva, recibirás una indicación para proceder, momento en el cual generarás la `consulta mongo:` peligrosa. Si es negativa, genera una `respuesta usuario:` informando que se canceló.
8.  **FORMATO:** Tu respuesta DEBE empezar SIEMPRE con `consulta mongo:` o `respuesta usuario:`, seguido de dos puntos y un espacio.

**Ejemplos de Secuencia Autónoma:**

*   *Usuario: "En la base de datos 'productos', busca los artículos con precio menor a 50 en la colección 'inventario' y dime cuántos hay."*
    *   *Tu Respuesta 1:* `consulta mongo: use productos`
    *   *(Sistema añade al historial: respuesta mongo: switched to db productos)*
    *   *Tu Respuesta 2:* `consulta mongo: db.inventario.find({{ price: {{ $lt: 50 }} }})`
    *   *(Sistema añade al historial: respuesta mongo: [resultado de la búsqueda])*
    *   *Tu Respuesta 3:* `consulta mongo: db.inventario.countDocuments({{ price: {{ $lt: 50 }} }})`
    *   *(Sistema añade al historial: respuesta mongo: 5)*
    *   *Tu Respuesta 4:* `respuesta usuario: Encontré 5 artículos con precio menor a 50 en la colección 'inventario' de la base de datos 'productos'. Los resultados de la búsqueda se mostraron previamente.`

*   *Usuario: "Muéstrame todas las bases de datos."*
    *   *Tu Respuesta 1:* `consulta mongo: show dbs`
    *   *(Sistema añade al historial: respuesta mongo: admin 0.000GB ... local 0.000GB)*
    *   *Tu Respuesta 2:* `respuesta usuario: Las bases de datos disponibles son admin, local, ...`

*   *Usuario: "Elimina la colección 'logs_viejos' de la base de datos 'auditoria'."*
    *   *Tu Respuesta 1:* `respuesta usuario: ¿Estás seguro de que quieres ejecutar db.logs_viejos.drop()?`
    *   *(Usuario confirma)*
    *   *(Sistema añade al historial: respuesta usuario: Confirmación recibida para db.logs_viejos.drop())* # O similar
    *   *Tu Respuesta 2:* `consulta mongo: use auditoria`
    *   *(Sistema añade al historial: respuesta mongo: switched to db auditoria)*
    *   *Tu Respuesta 3:* `consulta mongo: db.logs_viejos.drop()`
    *   *(Sistema añade al historial: respuesta mongo: true)*
    *   *Tu Respuesta 4:* `respuesta usuario: La colección 'logs_viejos' ha sido eliminada de la base de datos 'auditoria'.`

Historial de la conversación:
{history}

Entrada del usuario: {input}
Tu respuesta (con etiqueta):"""

PROMPT = PromptTemplate(input_variables=["history", "input"], template=TEMPLATE)

# --- API Endpoints ---

# --- Root Endpoint to serve index.html ---
@app.get("/")
async def read_index():
    """Serves the index.html file."""
    index_path = os.path.join(frontend_dir, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

# --- Existing API Endpoints ---
@app.post("/start_conversation", response_model=SessionResponse)
async def start_conversation():
    """
    Starts a new conversation session and returns a unique session ID.
    """
    session_id = str(uuid.uuid4())
    try:
        llm = GeminiLLM()
        # Use different prefixes for API context if needed, or keep as is
        memory = ConversationBufferMemory(memory_key="history", human_prefix="consulta usuario", ai_prefix="respuesta modelo")
        conversation = ConversationChain(
            llm=llm,
            prompt=PROMPT,
            verbose=False, # Set to True for debugging API requests
            memory=memory
        )
        conversations[session_id] = conversation
        logging_manager.log_debug("API", f"Started new session: {session_id}")
        return {"session_id": session_id}
    except Exception as e:
        logging_manager.log_debug("API Error", f"Failed to initialize session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize conversation: {str(e)}")


@app.post("/chat/{session_id}", response_model=ChatResponse)
async def chat(session_id: str, query: UserQuery):
    """
    Handles user interaction: initial query, LLM interaction, command execution,
    and UI-based confirmation for dangerous commands.
    """
    if session_id not in conversations:
        raise HTTPException(status_code=404, detail="Session not found")

    conversation = conversations[session_id]
    logging_manager.log_debug(f"API Chat [{session_id}] Received Query", query.model_dump_json()) # Log entire query

    # --- Determine Starting Input for LLM ---
    current_input = None
    initial_command_executed = False # Flag to track if we executed a confirmed command first

    if query.confirmed_command:
        # User confirmed a dangerous command via UI
        confirmed_cmd = query.confirmed_command
        logging_manager.log_debug(f"API Chat [{session_id}] Executing Confirmed Command", confirmed_cmd)
        # Security check again? Maybe not strictly needed if we trust the flow, but belt-and-suspenders:
        if not security.is_command_dangerous(confirmed_cmd):
             logging_manager.log_debug(f"API Chat [{session_id}] Warning", f"Confirmed command '{confirmed_cmd}' was not marked dangerous?")
             # Decide how to handle - proceed cautiously or error out? Let's proceed for now.

        try:
            output = executor.execute_mongo_command(confirmed_cmd)
            logging_manager.log_debug(f"API Chat [{session_id}] Confirmed Mongo Output", output)
            # Format response to feed back to LLM
            current_input = communication.create_respuesta_mongo(output)
            initial_command_executed = True
        except Exception as e:
            logging_manager.log_debug(f"API Chat [{session_id}] Error Executing Confirmed Command", str(e))
            return ChatResponse(status="error", response=f"Error executing confirmed command '{confirmed_cmd}': {str(e)}")

    elif query.user_query:
        # Normal user query
        current_input = query.user_query
        logging_manager.log_debug(f"API Chat [{session_id}] User Query", current_input)
    else:
        # Invalid request - needs either user_query or confirmed_command
        raise HTTPException(status_code=400, detail="Request must contain either 'user_query' or 'confirmed_command'")

    # --- LLM Interaction Loop ---
    MAX_ITERATIONS = 10
    for iteration in range(MAX_ITERATIONS):
        # If we already executed a confirmed command, this is the first LLM interaction *after* that.
        # If it was a normal user query, this is the first interaction.
        log_prefix = f"API Chat [{session_id}] Iteration {iteration+1}"
        if initial_command_executed and iteration == 0:
            log_prefix += " (Post-Confirmation)"

        logging_manager.log_debug(log_prefix, f"Input to LLM: {current_input}")

        try:
            # Get response from the model
            model_response_raw = conversation.predict(input=current_input)
            logging_manager.log_debug(f"API Chat [{session_id}] Raw Model Response", model_response_raw)

            # Process response
            label, content = communication.parse_message(model_response_raw)

            if not label:
                logging_manager.log_debug(f"API Chat [{session_id}] Parse Error", f"Could not parse: {model_response_raw}")
                # Save unparsed response to memory? Maybe just return error.
                # conversation.memory.save_context({"input": current_input}, {"output": f"respuesta usuario: {model_response_raw}"})
                return ChatResponse(status="error", response=f"Error: Unexpected model response format: {model_response_raw}")

            # Handle 'consulta mongo'
            if label == "consulta mongo":
                command_to_execute = content.strip()

                # Security Check
                if security.is_command_dangerous(command_to_execute):
                    logging_manager.log_debug(f"{log_prefix} Dangerous Command Detected", command_to_execute)
                    # --- STOP and Request UI Confirmation ---
                    return ChatResponse(
                        status="confirmation_required",
                        command_to_confirm=command_to_execute,
                        response=f"Confirmation needed in UI for command: {command_to_execute}" # Optional info message
                    )
                else:
                    # Execute safe command
                    logging_manager.log_debug(f"{log_prefix} Executing Safe Command", command_to_execute)
                    output = executor.execute_mongo_command(command_to_execute)
                    logging_manager.log_debug(f"{log_prefix} Mongo Output", output)

                    # Format response for the next LLM turn
                    respuesta_mongo_etiquetada = communication.create_respuesta_mongo(output)
                    logging_manager.log_debug(f"{log_prefix} Formatted Mongo Response", respuesta_mongo_etiquetada)

                    # Prepare for the next iteration
                    current_input = respuesta_mongo_etiquetada
                    # Continue the loop

            # Handle 'respuesta usuario'
            elif label == "respuesta usuario":
                logging_manager.log_debug(f"API Chat [{session_id}] Final User Response", content)
                # Task completed by the agent
                return ChatResponse(status="completed", response=content)

            else:
                # Unknown label
                logging_manager.log_debug(f"API Chat [{session_id}] Unknown Label", f"Label: {label}, Content: {content}")
                return ChatResponse(status="error", response=f"Error: Unknown label in model response: {label}")

        except Exception as e:
            logging_manager.log_debug(f"API Chat [{session_id}] Exception", str(e))
            # Consider saving context on error?
            return ChatResponse(status="error", response=f"An error occurred during processing: {str(e)}")

    # If loop finishes without returning, it means max iterations were hit
    logging_manager.log_debug(f"API Chat [{session_id}] Max Iterations Reached", f"Max iterations ({MAX_ITERATIONS}) reached.")
    return ChatResponse(status="error", response="Error: Maximum processing iterations reached.")


# --- Run Server (for local development) ---
if __name__ == "__main__":
    print("Starting MongoDB Agent API server...")
    print("Access the API docs at http://127.0.0.1:8000/docs")
    # Make sure logging is configured before starting server if needed
    # logging_manager.setup_logging() # Or however it's done
    uvicorn.run(app, host="127.0.0.1", port=8000)
