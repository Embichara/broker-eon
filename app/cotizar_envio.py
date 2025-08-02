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
        precio_total = obtener_precio_con_margen(origen, destino, usuario, tipo_unidad)
        if precio_total is not None:
            st.success(f"✅ Cotización sugerida: ${precio_total:,.2f} MXN")

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

import os

def obtener_precio_con_margen(origen, destino, cliente, unidad):
    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Obtener tarifa base
    cursor.execute("SELECT tarifa_base FROM tarifas WHERE origen = ? AND destino = ?", (origen, destino))
    resultado = cursor.fetchone()
    if not resultado:
        st.error("⚠️ No existe una tarifa base para esta ruta.")
        conn.close()
        return None
    tarifa_base = resultado[0]

    # 2. Buscar margen (cliente > unidad > general)
    margen = 0
    cursor.execute("SELECT margen_porcentaje FROM margenes WHERE criterio = 'cliente' AND valor = ?", (cliente,))
    res_cliente = cursor.fetchone()

    if res_cliente:
        margen = res_cliente[0]
    else:
        cursor.execute("SELECT margen_porcentaje FROM margenes WHERE criterio = 'unidad' AND valor = ?", (unidad,))
        res_unidad = cursor.fetchone()
        if res_unidad:
            margen = res_unidad[0]
        else:
            cursor.execute("SELECT margen_porcentaje FROM margenes WHERE criterio = 'general' AND valor = 'General'")
            res_general = cursor.fetchone()
            if res_general:
                margen = res_general[0]

    conn.close()

    # 3. Calcular precio final
    precio_final = tarifa_base * (1 + margen / 100)
    return precio_final