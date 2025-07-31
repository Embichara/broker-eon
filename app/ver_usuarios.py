import sqlite3

# Conectarse a la base de datos
conn = sqlite3.connect("eon.db")
cursor = conn.cursor()

# Obtener todos los usuarios
cursor.execute("SELECT id, nombre, correo, rol FROM usuarios")
usuarios = cursor.fetchall()

# Mostrar los resultados
print("📋 Usuarios en eon.db:")
for u in usuarios:
    print(u)

conn.close()