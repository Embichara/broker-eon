import sqlite3

# Conectarse a la base de datos principal
conn = sqlite3.connect("eon.db")
cursor = conn.cursor()

usuarios = [
    ("Emilio Bichara", "admin@eon.com", "admin123!", "admin"),
    ("Cliente Uno", "cliente1@correo.com", "cliente123!", "cliente"),
    ("Proveedor Uno", "proveedor1@correo.com", "proveedor123!", "proveedor")
]

for nombre, correo, contraseña, rol in usuarios:
    try:
        cursor.execute("""
            INSERT INTO usuarios (nombre, correo, contraseña, rol)
            VALUES (?, ?, ?, ?)
        """, (nombre, correo, contraseña, rol))
    except sqlite3.IntegrityError:
        print(f"⚠️ El correo {correo} ya existe, omitido.")

conn.commit()
conn.close()
print("✅ Usuarios insertados correctamente.")