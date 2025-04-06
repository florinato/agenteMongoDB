# security.py

def is_command_dangerous(command: str) -> bool:
    """
    Evalúa si el comando contiene palabras clave potencialmente peligrosas.
    Se buscan términos como 'drop', 'delete', 'remove', 'shutdown' o 'kill'.
    """
    dangerous_keywords = ["drop", "delete", "remove", "shutdown", "kill"]
    lower_command = command.lower()
    return any(keyword in lower_command for keyword in dangerous_keywords)

def request_authorization() -> bool:
    """
    Solicita autorización al usuario para ejecutar un comando peligroso.
    """
    user_input = input("El comando parece peligroso. ¿Desea proceder? (s/n): ")
    return user_input.strip().lower() == 's'
