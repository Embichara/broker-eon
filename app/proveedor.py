import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

def ofertar(usuario_proveedor):
    st.subheader("📢 Ofertar sobre cotizaciones disponibles")

    conn = sqlite3.connect("eon.db")
    cursor = conn.cursor()

    # Consulta cotizaciones aún no ofertadas por este proveedor
    query = """
        SELECT c.id, c.cliente, c.origen, c.destino, c.tipo_unidad, c.descripcion_paquete, c.peso_kg, c.distancia_km, c.precio_total, c.fecha
        FROM cotizaciones c
        WHERE c.id NOT IN (
            SELECT id_cotizacion FROM ofertas WHERE proveedor = ?
        )
        ORDER BY c.fecha DESC
    """
    cotizaciones = pd.read_sql_query(query, conn, params=(usuario_proveedor,))

    if cotizaciones.empty:
        st.info("No hay cotizaciones nuevas disponibles o ya ofertaste en todas.")
        conn.close()
        return

    st.dataframe(cotizaciones, use_container_width=True)

    id_cotizacion = st.selectbox("Selecciona una cotización para ofertar:", cotizaciones["id"])
    precio_ofertado = st.number_input("💰 Precio ofertado (MXN)", min_value=1.0)
    mensaje = st.text_area("📝 Mensaje al cliente")

    if st.button("Enviar oferta"):
        cursor.execute("""
            INSERT INTO ofertas (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha)
            VALUES (?, ?, ?, ?, ?)
        """, (id_cotizacion, usuario_proveedor, precio_ofertado, mensaje, str(date.today())))
        conn.commit()
        st.success("✅ Oferta enviada con éxito.")
        st.rerun()

    conn.close()

def vista_proveedor(usuario_proveedor):
    st.subheader(f"👤 Bienvenido, {usuario_proveedor}")
    opcion = st.selectbox("Selecciona una opción:", ["Ofertar sobre cotizaciones"])

    if opcion == "Ofertar sobre cotizaciones":
        ofertar(usuario_proveedor)