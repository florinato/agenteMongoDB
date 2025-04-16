# test_executor.py
# test_executor.py
import sys  # Mantener sys solo para sys.exit

# import os # No es necesario

# Ya no se necesita manipular sys.path

try:
    # Usar importaciones directas ya que todos los .py están en la raíz
    import executor
    import logging_manager
    print("Módulos importados correctamente.")
except ImportError as e:
    print(f"Error al importar módulos: {e}")
    sys.exit(1)

# Comandos a probar
test_commands = [
    "use test",             # Cambiar a la BD 'test'
    "db.getName()",         # Confirmar BD actual
    # Insertar datos para crear físicamente la BD y una colección (Sintaxis corregida)
    "db.test_collection.insertMany([{ name: 'Alice', age: 30 }, { name: 'Bob', age: 25 }])",
    "show collections",     # Comando simple (ahora debería mostrar 'test_collection')
    "db.getCollectionNames()", # Método JS (ahora debería incluir 'test_collection')
    "db.test_collection.countDocuments()", # Contar documentos insertados
    "use historias",        # Cambiar a 'historias'
    "db.getName()",         # Confirmar BD actual
    "db.getCollectionNames()", # Colecciones en 'historias'
    "use wallapop-clone",   # Cambiar a 'wallapop-clone'
    "db.getName()",         # Confirmar BD actual
    "db.getCollectionNames()", # Colecciones en 'wallapop-clone'
    "print('hello world')", # Comando JS simple para ver salida
    "use test; db.test_chain.insertOne({ message: 'chained command test' }); db.test_chain.find()", # Comando encadenado (Known issue: only first part executes)
]

print("\n--- Iniciando Test de Executor ---")

for command in test_commands:
    print(f"\n>>> Ejecutando Comando: {command}")
    try:
        output = executor.execute_mongo_command(command)
        print(f"<<< Salida Recibida:\n{output}")
        print("-" * 20)
    except Exception as e:
        print(f"!!! Excepción durante la ejecución: {e}")
        print("-" * 20)

print("\n--- Test de Executor Finalizado ---")

# Opcional: Mostrar el log generado durante el test
# print("\n--- Contenido del Log ---")
# print(logging_manager.get_log())
# print("------------------------")
