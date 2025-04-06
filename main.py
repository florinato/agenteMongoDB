# main.py
import os
import re

# Langchain imports
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts.prompt import PromptTemplate

# Local imports
import communication
import executor
import logging_manager
import security
from model_integration import GeminiLLM  # Importar la clase LLM directamente

# Definir la plantilla del prompt para Langchain
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


def main():
    # Inicializar LLM, Memoria y Cadena de Conversación
    llm = GeminiLLM()
    memory = ConversationBufferMemory(memory_key="history", human_prefix="consulta usuario", ai_prefix="respuesta modelo") # Usar prefijos personalizados si es necesario
    conversation = ConversationChain(
        llm=llm,
        prompt=PROMPT,
        verbose=False, # Poner a True para ver el prompt completo enviado a Langchain
        memory=memory
    )

    log_file_path = os.path.abspath(logging_manager.LOG_FILE)
    print("Agente Mongo con Gemini (Langchain): Iniciando sesión...")
    print(f"Las interacciones de depuración se guardarán en: {log_file_path}")

    # Bucle principal de interacción con el usuario
    while True:
        user_query = input("Ingrese su consulta (o 'salir' para terminar): ")
        if user_query.lower() == 'salir':
            print("Finalizando sesión.")
            break

        logging_manager.log_debug("User Query", user_query)

        # Variable para pasar la entrada al modelo en cada iteración
        current_input = user_query
        is_first_iteration = True

        # Bucle de iteración autónoma para una consulta de usuario
        while True:
            # Determinar el prefijo correcto para la memoria basado en si es la consulta inicial o una respuesta mongo
            # Esto es un HACK porque ConversationBufferMemory no maneja bien roles intermedios.
            # Idealmente, usaríamos un tipo de memoria diferente o un Agente.
            # if not is_first_iteration:
            #     # Forzar el prefijo humano para la respuesta mongo (para que el LLM la vea como entrada)
            #     # Esto puede ensuciar el historial si se ve directamente.
            #     memory.human_prefix = "respuesta mongo" # Temporalmente cambiar prefijo
            # else:
            #     memory.human_prefix = "consulta usuario" # Prefijo normal

            # Obtener respuesta del modelo
            # Langchain añade automáticamente el 'current_input' al historial con el prefijo adecuado (human_prefix)
            model_response_raw = conversation.predict(input=current_input)
            logging_manager.log_debug(f"Respuesta Modelo Raw (Iteración {'Inicial' if is_first_iteration else 'Interna'})", model_response_raw)

            # Restaurar prefijo por si lo cambiamos (si usamos el hack anterior)
            # memory.human_prefix = "consulta usuario"

            # Procesar respuesta
            label, content = communication.parse_message(model_response_raw)

            if not label:
                logging_manager.log_debug("Error Parseo", f"No se pudo parsear: {model_response_raw}")
                print(f"Error: Respuesta inesperada del modelo: {model_response_raw}")
                # Guardar la respuesta no parseada en memoria como respuesta de IA
                # El input fue 'current_input'
                conversation.memory.save_context({"input": current_input}, {"output": f"respuesta usuario: {model_response_raw}"})
                break # Salir del bucle interno en caso de error de parseo

            # Ejecutar si es consulta mongo
            if label == "consulta mongo":
                is_first_iteration = False # Ya no es la primera iteración

                # Validación de comandos peligrosos
                if security.is_command_dangerous(content):
                    print(f"Comando Peligroso Detectado: {content}")
                    if not security.request_authorization():
                        print("Autorización denegada. Abortando secuencia.")
                        # Guardar que se abortó
                        conversation.memory.save_context(
                            {"input": current_input}, # El input que llevó a la consulta peligrosa
                            {"output": "respuesta usuario: Comando peligroso detectado y autorización denegada."} # La respuesta del modelo fue la consulta
                        )
                        break # Salir del bucle interno
                    else:
                        print("Autorización concedida. Ejecutando comando.")
                        # Continuar con la ejecución

                # Ejecutar el comando
                command_to_execute = content.strip()
                output = executor.execute_mongo_command(command_to_execute)
                logging_manager.log_debug("Salida Mongo", output)

                # Crear respuesta etiquetada y mostrarla al usuario
                respuesta_mongo_etiquetada = communication.create_respuesta_mongo(output)
                logging_manager.log_debug("Respuesta Mongo Etiquetada", respuesta_mongo_etiquetada)
                print(respuesta_mongo_etiquetada) # Mostrar pasos intermedios

                # Preparar la respuesta mongo como la *siguiente entrada* para el modelo
                current_input = respuesta_mongo_etiquetada

                # Guardar en memoria: La IA dijo 'consulta mongo', el sistema respondió con 'respuesta mongo'
                # Langchain ya guardó (current_input -> model_response_raw)
                # Necesitamos añadir manualmente el resultado para el siguiente turno.
                # El workaround anterior de save_context puede ser confuso aquí.
                # La forma en que Langchain ConversationChain maneja esto no es ideal para agentes.
                # Vamos a confiar en que el LLM use el historial correctamente.
                # El historial ahora tendrá:
                # Humano (user_query) -> IA (consulta mongo)
                # Humano (respuesta mongo) -> IA (siguiente consulta mongo o respuesta usuario)
                # Esto requiere que el LLM entienda que 'respuesta mongo' es la entrada para su siguiente decisión.

                # Continuar el bucle interno para el siguiente paso autónomo

            elif label == "respuesta usuario":
                # Si el modelo dio una respuesta directa al usuario, la tarea terminó.
                logging_manager.log_debug("Respuesta Usuario Final", model_response_raw)
                print(model_response_raw)
                # Guardar la respuesta final en memoria (Langchain ya lo hizo con predict)
                # conversation.memory.save_context({"input": current_input}, {"output": model_response_raw})
                break # Salir del bucle interno, volver a esperar input del usuario

            else:
                # Error de etiqueta desconocida
                print(f"Error: Etiqueta desconocida o formato incorrecto: {model_response_raw}")
                logging_manager.log_debug("Error Etiqueta", f"Etiqueta desconocida: {model_response_raw}")
                # Guardar respuesta no reconocida
                conversation.memory.save_context({"input": current_input}, {"output": f"respuesta usuario: {model_response_raw}"})
                break # Salir del bucle interno


if __name__ == "__main__":
    main()
