import sqlite3

def crear_tablas():
    conn = sqlite3.connect("eon.db")
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            contraseña TEXT NOT NULL,
            rol TEXT CHECK(rol IN ('admin', 'cliente', 'proveedor')) NOT NULL
        )
    ''')

    conn.commit()
    conn.close()