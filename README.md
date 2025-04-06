# Agente MongoDB con Gemini (Langchain)

## Descripción

Este proyecto implementa un agente conversacional basado en el modelo de lenguaje Gemini (a través de Langchain) que permite a los usuarios interactuar con una base de datos MongoDB utilizando lenguaje natural. El agente traduce las peticiones del usuario en comandos `mongosh`, los ejecuta secuencialmente y devuelve los resultados o una respuesta final al usuario.

![Agent Architecture Diagram](Captura%20de%20pantalla%202025-04-06%20122310.png)

## Características Principales

*   **Interacción en Lenguaje Natural:** Permite realizar consultas y operaciones en MongoDB sin necesidad de escribir comandos `mongosh` directamente.
*   **Integración con Gemini LLM:** Utiliza el modelo Gemini-2.0-flash-001 (configurable en `model_integration.py`) para interpretar las intenciones del usuario y generar los comandos adecuados.
*   **Ejecución Secuencial de Comandos:** Capaz de manejar tareas que requieren múltiples pasos (ej. seleccionar una base de datos y luego realizar una consulta) manteniendo el contexto entre interacciones.
*   **Manejo de Contexto:** Recuerda la base de datos seleccionada (`use <db>`) entre comandos dentro de una misma sesión de consulta.
*   **Seguridad:** Detecta comandos potencialmente peligrosos (como `dropDatabase`, `drop`, `delete`) y solicita confirmación explícita al usuario antes de ejecutarlos.
*   **Registro Detallado:** Guarda un registro de las interacciones y los comandos ejecutados en `mongo_agent.log` para depuración.

## Cómo Funciona (Flujo de Trabajo)

1.  **Inicio:** El script `main.py` inicializa el modelo LLM (Gemini), la memoria de conversación (Langchain `ConversationBufferMemory`) y la cadena de conversación (`ConversationChain`) con un prompt detallado que instruye al modelo sobre su rol y cómo interactuar.
2.  **Entrada del Usuario:** El usuario introduce una consulta en lenguaje natural (ej. "Muéstrame las colecciones en la base de datos 'test'").
3.  **Procesamiento LLM (Iteración 1):** La consulta se envía al LLM. Basándose en el prompt y el historial (si existe), el LLM genera una respuesta formateada:
    *   `consulta mongo: <comando>`: Si necesita ejecutar un comando MongoDB.
    *   `respuesta usuario: <mensaje>`: Si puede responder directamente o si ha completado la tarea.
    *   `respuesta usuario: ¿Estás seguro...?`: Si detecta un comando peligroso.
4.  **Ejecución del Comando (si aplica):**
    *   Si la respuesta es `consulta mongo:`, el script extrae el comando.
    *   **Validación de Seguridad:** Se verifica si el comando es peligroso (`security.py`). Si lo es, se pide confirmación al usuario. Si se deniega, el proceso se detiene para esa consulta.
    *   **Ejecución:** El comando validado se ejecuta contra MongoDB usando `executor.py`.
    *   **Resultado:** La salida del comando se captura.
5.  **Retroalimentación al LLM (Iteración 2+):**
    *   El resultado del comando se formatea como `respuesta mongo: <resultado>` (`communication.py`).
    *   Esta respuesta formateada se envía de **vuelta al LLM** como la nueva entrada.
    *   El LLM analiza el resultado y decide el siguiente paso (otro `consulta mongo:` o una `respuesta usuario:` final).
    *   Este ciclo continúa hasta que el LLM genera una `respuesta usuario:`.
6.  **Respuesta Final:** Cuando el LLM genera `respuesta usuario:`, el mensaje se muestra al usuario final y el agente espera la siguiente consulta.
7.  **Salida:** El bucle termina cuando el usuario escribe 'salir'.

## Módulos Principales

*   **`main.py`:** Orquesta el flujo principal de la aplicación, maneja la interacción con el usuario y el ciclo de conversación con el LLM.
*   **`model_integration.py`:** Define la clase `GeminiLLM` que interactúa con la API de Gemini (o el modelo configurado). Requiere configuración de API Key (probablemente mediante variables de entorno, ver sección Configuración).
*   **`executor.py`:** Contiene la función `execute_mongo_command` que se conecta a MongoDB (usando `pymongo`) y ejecuta los comandos `mongosh` recibidos. Requiere la URI de conexión a MongoDB.
*   **`communication.py`:** Proporciona funciones para parsear los mensajes del LLM (`parse_message`) y formatear las respuestas del sistema (`create_respuesta_mongo`).
*   **`security.py`:** Implementa la lógica para detectar comandos peligrosos (`is_command_dangerous`) y solicitar autorización al usuario (`request_authorization`).
*   **`logging_manager.py`:** Configura y gestiona el registro de eventos en el archivo `mongo_agent.log`.
*   **`requirements.txt`:** Lista las dependencias Python necesarias.
*   **`.env` (No incluido, crear manualmente):** Archivo para almacenar variables de entorno sensibles como la API Key de Gemini y la URI de MongoDB.

## Cómo Ejecutar

1.  **Clonar el repositorio (si aplica).**
2.  **Crear un entorno virtual (recomendado):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Linux/macOS
    venv\Scripts\activate    # En Windows
    ```
3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configurar Variables de Entorno:**
    *   Crea un archivo llamado `.env` en la raíz del proyecto.
    *   Añade las siguientes variables con tus valores:
        ```dotenv
        GEMINI_API_KEY=TU_API_KEY_DE_GEMINI
        MONGO_URI=mongodb://usuario:contraseña@host:puerto/ # O tu URI de conexión
        ```
    *   *Nota:* El código actual podría necesitar ajustes para cargar explícitamente estas variables desde `.env` (ej. usando `python-dotenv`). Asegúrate de que `model_integration.py` y `executor.py` accedan a estas variables.
5.  **Ejecutar el agente:**
    ```bash
    python main.py
    ```
6.  **Interactuar:** Escribe tus consultas en la terminal cuando se te solicite. Escribe `salir` para terminar.

## Consideraciones de Seguridad

*   **Gestión de Credenciales:** La API Key de Gemini y la URI de MongoDB son sensibles. Utiliza variables de entorno y el archivo `.env` (añadido a `.gitignore`) para gestionarlas de forma segura. No las incluyas directamente en el código.
*   **Permisos de MongoDB:** Asegúrate de que el usuario de MongoDB especificado en la URI tenga los permisos mínimos necesarios para las operaciones que el agente debe realizar.
*   **Validación de Comandos:** Aunque existe una capa de seguridad para comandos peligrosos, revisa y ajusta la lista en `security.py` según tus necesidades específicas.
