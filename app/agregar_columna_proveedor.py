import sqlite3

conn = sqlite3.connect("eon.db")
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE cotizaciones ADD COLUMN proveedor_asignado TEXT")
    print("✅ Columna 'proveedor_asignado' agregada.")
except sqlite3.OperationalError:
    print("⚠️ La columna ya existe. No se realizó ningún cambio.")

conn.commit()
conn.close()