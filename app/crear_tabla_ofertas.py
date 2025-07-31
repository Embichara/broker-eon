import sqlite3

conn = sqlite3.connect("eon.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cotizacion INTEGER,
    proveedor TEXT,
    precio_ofertado REAL,
    mensaje TEXT,
    fecha TEXT DEFAULT (DATE('now')),
    FOREIGN KEY (id_cotizacion) REFERENCES cotizaciones(id)
)
""")

conn.commit()
conn.close()
print("✅ Tabla 'ofertas' creada correctamente.")