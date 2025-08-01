import streamlit as st
import sqlite3
from datetime import date
from pdf_generator import generar_pdf_cotizacion
import uuid

def cotizar_envio(usuario):
    st.subheader("📦 Cotización de Envío")

    if "origen" not in st.session_state:
        st.session_state.origen = ""
    if "destino" not in st.session_state:
        st.session_state.destino = ""
    if "distancia" not in st.session_state:
        st.session_state.distancia = 1
    if "peso" not in st.session_state:
        st.session_state.peso = 0.1
    if "descripcion" not in st.session_state:
        st.session_state.descripcion = ""
    if "tipo_unidad" not in st.session_state:
        st.session_state.tipo_unidad = "Camioneta"

    origen = st.text_input("Origen", key="origen")
    destino = st.text_input("Destino", key="destino")
    distancia = st.number_input("Distancia estimada (km)", min_value=1, key="distancia")
    peso = st.number_input("Peso del paquete (kg)", min_value=0.1, key="peso")
    descripcion = st.text_area("Descripción del paquete", key="descripcion")
    tipo_unidad = st.selectbox("Tipo de unidad requerida", 
        ["Camioneta", "Camión 3.5 t", "Tráiler", "Caja seca", "Caja refrigerada"], 
        key="tipo_unidad"
    )

    if st.button("Calcular cotización"):
        precio_por_km = 10  # Precio fijo por kilómetro
        precio_total = distancia * precio_por_km

        cotizacion_id = str(uuid.uuid4())[:8]
        estatus_url = f"https://eonlogisticgroup.com/estatus/{cotizacion_id}"

        datos = {
            "cotizacion_id": cotizacion_id,
            "fecha": str(date.today()),
            "origen": origen,
            "destino": destino,
            "distancia": distancia,
            "peso": peso,
            "descripcion_paquete": descripcion,
            "tipo_unidad": tipo_unidad,
            "precio_total": precio_total,
            "cliente": usuario,
            "estatus_url": estatus_url
        }

        conn = sqlite3.connect("eon.db")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cotizacion_id TEXT,
                cliente TEXT,
                origen TEXT,
                destino TEXT,
                distancia_km REAL,
                peso_kg REAL,
                descripcion_paquete TEXT,
                tipo_unidad TEXT,
                precio_total REAL,
                fecha TEXT,
                estatus_url TEXT,
                archivo_pdf TEXT,
                proveedor_asignado TEXT
            )
        """)

        cursor.execute("""
            INSERT INTO cotizaciones (
                cotizacion_id, cliente, origen, destino, distancia_km, peso_kg,
                descripcion_paquete, tipo_unidad, precio_total, fecha, estatus_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datos["cotizacion_id"], datos["cliente"], datos["origen"], datos["destino"],
            datos["distancia"], datos["peso"], datos["descripcion_paquete"],
            datos["tipo_unidad"], datos["precio_total"], datos["fecha"], datos["estatus_url"]
        ))

        conn.commit()
        conn.close()

        st.success(f"✅ Cotización generada: ${precio_total:,.2f} MXN")

        archivo = generar_pdf_cotizacion(datos, f"cotizacion_{usuario}.pdf")
        st.download_button(
            label="📄 Descargar cotización PDF",
            data=open(archivo, "rb"),
            file_name=archivo.split("/")[-1],
            mime="application/pdf"
        )