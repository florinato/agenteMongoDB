# communication.py

def create_consulta_usuario(message: str) -> str:
    """Formato para una consulta del usuario."""
    return f"consulta usuario: {message}"

def create_respuesta_usuario(message: str) -> str:
    """Formato para la respuesta al usuario."""
    return f"respuesta usuario: {message}"

def create_consulta_mongo(command: str) -> str:
    """Formato para la consulta a mongo."""
    return f"consulta mongo: {command}"

def create_respuesta_mongo(output: str) -> str:
    """Formato para la respuesta de mongo."""
    return f"respuesta mongo: {output}"

def parse_message(message: str):
    """
    Parsea un mensaje con formato 'etiqueta: contenido' y devuelve la tupla (etiqueta, contenido).
    Si no se encuentra el separador, devuelve (None, message).
    Parsea un mensaje buscando 'etiqueta: contenido' (etiqueta siendo 'consulta mongo' o 'respuesta usuario').
    Ignora texto previo a la etiqueta (como timestamps).
    Si no se encuentra el patrón, devuelve (None, message).
    """
    import re  # Importar re aquí o al principio del archivo

    # Buscar el patrón 'etiqueta: contenido', permitiendo texto antes
    # Se busca 'consulta mongo:' o 'respuesta usuario:' seguido de ':' y el resto
    match = re.search(r"(consulta mongo|respuesta usuario):\s*(.*)", message, re.DOTALL)

    if match:
        label = match.group(1).strip() # La etiqueta encontrada
        content = match.group(2).strip() # El contenido después de ':'
        return label, content
    else:
        # Si no se encuentra el patrón específico, devolver None y el mensaje original
        return None, message
