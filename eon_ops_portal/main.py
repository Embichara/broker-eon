# EON OPS DASHBOARD - Streamlit Structure (Base Multipage)

import os
import sys
import uuid
import sqlite3
import smtplib
import requests
import pandas as pd
import streamlit as st
from fpdf import FPDF
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

# ----------------------------------------------------
# Config inicial de Streamlit (debe ir antes de UI)
# ----------------------------------------------------
st.set_page_config(page_title="EON OPS Portal", page_icon="🚚", layout="wide")

# ----------------------------------------------------
# Carga de entorno y sys.path para el paquete carriers
# ----------------------------------------------------
load_dotenv()
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from carriers.dhl_client import cotizar_dhl, normalizar_ofertas_dhl  # requiere carriers/dhl_client.py

# -----------------------------------------
# DB Helpers: path y asegurado de estructura
# -----------------------------------------
DB_PATH = os.path.abspath("eon.db")

def ensure_db_schema():
    """Crea/ajusta todas las tablas e índices necesarios para la app."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Tabla principal de cotizaciones
    c.execute("""
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
            proveedor_asignado TEXT,
            estatus TEXT DEFAULT 'Pendiente por asignar'
        )
    """)

    # Columnas defensivas (por si existía una versión antigua)
    for col_def in [
        ("estatus", "TEXT DEFAULT 'Pendiente por asignar'"),
        ("cotizacion_id", "TEXT"),
        ("estatus_url", "TEXT"),
        ("proveedor_asignado", "TEXT"),
        ("precio_total", "REAL")
    ]:
        try:
            c.execute(f"ALTER TABLE cotizaciones ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    # Tarifas con UNIQUE(origen, destino) para ON CONFLICT
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarifas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origen TEXT,
            destino TEXT,
            tarifa_base REAL,
            UNIQUE(origen, destino)
        )
    """)

    # Márgenes con UNIQUE(criterio, valor)
    c.execute("""
        CREATE TABLE IF NOT EXISTS margenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criterio TEXT,   -- 'unidad' / 'peso' / 'general'
            valor TEXT,
            margen_porcentaje REAL,
            UNIQUE(criterio, valor)
        )
    """)

    # Márgenes por peso
    c.execute("""
        CREATE TABLE IF NOT EXISTS margenes_peso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rango_min REAL,
            rango_max REAL,
            margen_porcentaje REAL
        )
    """)

    # Proveedores por ruta
    c.execute("""
        CREATE TABLE IF NOT EXISTS proveedores_rutas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor TEXT,
            origen TEXT,
            destino TEXT,
            tipo_unidad TEXT,
            factor_precio REAL
        )
    """)

    # Ofertas de proveedores
    c.execute("""
        CREATE TABLE IF NOT EXISTS ofertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cotizacion INTEGER,
            proveedor TEXT,
            precio_ofertado REAL,
            mensaje TEXT,
            fecha TEXT
        )
    """)

    # Usuarios (para buscar correo al enviar PDF)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            correo TEXT
        )
    """)

    conn.commit()
    conn.close()

ensure_db_schema()

# ------------------
# Utilidades de mail
# ------------------
def enviar_email(destinatario, asunto, cuerpo, archivo_pdf=None):
    EMAIL = os.getenv("EMAIL")
    PASSWORD = os.getenv("PASSWORD")

    if not EMAIL or not PASSWORD:
        print("⚠️ Falta EMAIL y/o PASSWORD en .env para envío SMTP.")
        return False

    mensaje = EmailMessage()
    mensaje['Subject'] = asunto
    mensaje['From'] = EMAIL
    mensaje['To'] = destinatario
    mensaje.set_content(cuerpo)

    if archivo_pdf:
        with open(archivo_pdf, "rb") as f:
            mensaje.add_attachment(f.read(), maintype='application', subtype='pdf', filename=os.path.basename(archivo_pdf))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL, PASSWORD)
            smtp.send_message(mensaje)
        return True
    except Exception as e:
        print(f"Error al enviar correo: {e}")
        return False

# -----------------------------
# Generador de PDF de cotizacion
# -----------------------------
def generar_pdf_cotizacion(datos, nombre_archivo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, "Cotización de Envío - Eon Logistics", ln=True, align="C")
    pdf.ln(10)

    pdf.cell(0, 10, f"Cliente: {datos['cliente']}", ln=True)
    if datos.get("proveedor_asignado"):  # pásalo vacío si quieres ocultarlo
        pdf.cell(0, 10, f"Proveedor Asignado: {datos['proveedor_asignado']}", ln=True)

    pdf.cell(0, 10, f"Origen: {datos['origen']}", ln=True)
    pdf.cell(0, 10, f"Destino: {datos['destino']}", ln=True)
    pdf.cell(0, 10, f"Tipo de unidad: {datos['tipo_unidad']}", ln=True)
    pdf.cell(0, 10, f"Peso: {datos['peso_kg']} kg", ln=True)
    pdf.multi_cell(0, 10, f"Descripción: {datos['descripcion_paquete']}")
    pdf.cell(0, 10, f"Precio total: ${datos['precio_total']:,.2f}", ln=True)
    pdf.cell(0, 10, f"Fecha: {datos['fecha']}", ln=True)

    seguimiento_url = f"https://eonlogisticgroup.com/estatus/{datos['cotizacion_id']}"
    pdf.ln(10)
    pdf.set_text_color(0, 0, 255)
    pdf.cell(0, 10, f"Seguimiento en línea: {seguimiento_url}", ln=True, link=seguimiento_url)
    pdf.set_text_color(0, 0, 0)

    out_dir = os.path.abspath("../app/cotizaciones_pdf")
    os.makedirs(out_dir, exist_ok=True)
    ruta_pdf = os.path.join(out_dir, nombre_archivo)
    pdf.output(ruta_pdf)
    return ruta_pdf

# -----------------------------
# UI: Nueva cotización (Manual)
# -----------------------------
def nueva_cotizacion_manual():
    st.subheader("📝 Nueva Cotización (Manual)")

    origen = st.text_input("Origen")
    destino = st.text_input("Destino")
    tipo_unidad = st.selectbox("Tipo de unidad", ["Camioneta", "Camión 3.5t", "Tráiler", "Caja Seca", "Caja Refrigerada"])
    peso = st.number_input("Peso del paquete (kg)", min_value=0.1, value=1.0)
    descripcion = st.text_area("Descripción del paquete")
    cliente = st.text_input("Nombre del cliente")

    if st.button("💾 Guardar cotización"):
        if not origen or not destino or not cliente or peso <= 0:
            st.warning("Por favor llena todos los campos correctamente.")
            return

        cotizacion_id = str(uuid.uuid4())[:8]
        estatus_url = f"https://eonlogisticgroup.com/estatus/{cotizacion_id}"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 1) Tarifa base por ruta
        c.execute("SELECT tarifa_base FROM tarifas WHERE origen = ? AND destino = ?", (origen, destino))
        row_tarifa = c.fetchone()
        if not row_tarifa:
            conn.close()
            st.error("No se encontró una tarifa base para esta ruta. Configúrala en el módulo de Pricing.")
            return
        tarifa_base = row_tarifa[0]

        # 2) Margen por unidad
        c.execute("SELECT margen_porcentaje FROM margenes WHERE criterio = 'unidad' AND valor = ?", (tipo_unidad,))
        row_margen_uni = c.fetchone()
        if not row_margen_uni:
            conn.close()
            st.error(f"No se encontró un margen de utilidad para la unidad: {tipo_unidad}. Configúralo en el módulo de Pricing.")
            return
        margen_unidad = row_margen_uni[0]

        # 3) Margen por peso
        c.execute("SELECT margen_porcentaje FROM margenes_peso WHERE ? BETWEEN rango_min AND rango_max", (peso,))
        row_margen_peso = c.fetchone()
        if not row_margen_peso:
            conn.close()
            st.error(f"No se encontró un margen de utilidad para el peso: {peso} kg. Configúralo en el módulo de Pricing.")
            return
        margen_peso = row_margen_peso[0]

        # 4) Cálculo del precio
        precio_sin_margen = tarifa_base * peso
        precio_total = precio_sin_margen * (1 + margen_unidad / 100) * (1 + margen_peso / 100)

        # 5) Insertar cotización
        c.execute("""
            INSERT INTO cotizaciones (
                cotizacion_id, cliente, origen, destino, distancia_km, peso_kg,
                descripcion_paquete, tipo_unidad, precio_total, fecha, estatus_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cotizacion_id, cliente, origen, destino, 0, peso,
            descripcion, tipo_unidad, precio_total, str(date.today()), estatus_url
        ))
        id_cotizacion = c.lastrowid

        # 6) Ofertas automáticas
        c.execute("""
            SELECT proveedor, factor_precio FROM proveedores_rutas
            WHERE origen = ? AND destino = ? AND tipo_unidad = ?
        """, (origen, destino, tipo_unidad))
        proveedores = c.fetchall()

        hoy = datetime.now().strftime("%Y-%m-%d")
        for proveedor, factor in proveedores:
            precio_ofertado = precio_total * factor
            msg = f"Oferta automática generada para {proveedor}"
            c.execute("""
                INSERT INTO ofertas (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha)
                VALUES (?, ?, ?, ?, ?)
            """, (id_cotizacion, proveedor, precio_ofertado, msg, hoy))

        conn.commit()
        conn.close()

        st.success(f"Cotización generada automáticamente: ${precio_total:,.2f} MXN")
        st.caption(f"Estatus URL: {estatus_url}")
        if proveedores:
            st.info(f"Se generaron {len(proveedores)} ofertas automáticas.")

# -----------------------------------------
# UI: Cotizaciones pendientes por asignar
# -----------------------------------------
def cotizaciones_pendientes():
    st.subheader("📋 Cotizaciones Pendientes por Asignar")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cotizacion_id, cliente, origen, destino, tipo_unidad, descripcion_paquete, precio_total, fecha, proveedor_asignado
        FROM cotizaciones
        ORDER BY fecha DESC
    """, conn)
    conn.close()

    df_pend = df[df["proveedor_asignado"].isnull() | (df["proveedor_asignado"] == "")]
    if df_pend.empty:
        st.info("No hay cotizaciones pendientes por asignar.")
        return

    st.dataframe(df_pend, use_container_width=True)

    seleccion = st.selectbox(
        "Selecciona una cotización para ver detalles:",
        [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in df_pend.iterrows()]
    )
    cot_id = int(seleccion.split(" - ")[0])
    cot = df_pend[df_pend["id"] == cot_id].iloc[0]

    st.write(f"**Cliente:** {cot['cliente']}")
    st.write(f"**Origen:** {cot['origen']}")
    st.write(f"**Destino:** {cot['destino']}")
    st.write(f"**Tipo de unidad:** {cot['tipo_unidad']}")
    st.write(f"**Descripción:** {cot['descripcion_paquete']}")
    st.write(f"**Precio total:** ${cot['precio_total']:,.2f}")
    st.write(f"**Fecha de creación:** {cot['fecha']}")

    st.markdown("---")
    st.subheader("Asignar Proveedor")

    proveedor = st.text_input("Nombre del Proveedor")
    if st.button("✅ Asignar Proveedor"):
        if not proveedor.strip():
            st.warning("Debes ingresar el nombre de un proveedor.")
            return

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE cotizaciones
            SET proveedor_asignado = ?, estatus = 'Asignado'
            WHERE id = ?
        """, (proveedor.strip(), cot_id))
        conn.commit()
        conn.close()

        st.success(f"Proveedor '{proveedor}' asignado correctamente a la cotización ID {cot_id}.")

        # Envío de PDF al cliente SIN mostrar proveedor
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT correo FROM usuarios WHERE nombre = ?", (cot['cliente'],))
        row_cli = c.fetchone()
        conn.close()

        if row_cli and row_cli[0]:
            correo_cliente = row_cli[0]
            datos_pdf = {
                "cliente": cot['cliente'],
                "proveedor_asignado": "",  # oculto al cliente
                "origen": cot['origen'],
                "destino": cot['destino'],
                "tipo_unidad": cot['tipo_unidad'],
                "peso_kg": cot.get('peso_kg', 0),
                "descripcion_paquete": cot['descripcion_paquete'],
                "precio_total": cot['precio_total'],
                "fecha": cot['fecha'],
                "cotizacion_id": cot['cotizacion_id']
            }
            nombre_pdf = f"cotizacion_{cot['cotizacion_id']}.pdf"
            ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)

            asunto = "📦 Cotización Asignada - Eon Logistics"
            cuerpo = (f"Hola {cot['cliente']},\n\n"
                      "Tu cotización ha sido procesada.\n"
                      "Adjunto encontrarás el PDF con los detalles.\n\n"
                      "Gracias por confiar en Eon Logistics.")

            exito = enviar_email(correo_cliente, asunto, cuerpo, ruta_pdf)
            if exito:
                st.success(f"Correo enviado correctamente a {correo_cliente}.")
            else:
                st.error("❌ No se pudo enviar el correo al cliente.")
        else:
            st.warning("⚠️ No se encontró el correo del cliente en 'usuarios'.")

        st.rerun()

# ------------------------------------
# UI: Cotizaciones con proveedor asign
# ------------------------------------
def cotizaciones_asignadas():
    st.subheader("📑 Cotizaciones Asignadas")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cotizacion_id, cliente, origen, destino, tipo_unidad, descripcion_paquete, precio_total, fecha, proveedor_asignado
        FROM cotizaciones
        WHERE proveedor_asignado IS NOT NULL AND proveedor_asignado != ''
        ORDER BY fecha DESC
    """, conn)
    conn.close()

    if df.empty:
        st.info("No hay cotizaciones asignadas.")
        return

    st.dataframe(df, use_container_width=True)

    seleccion = st.selectbox(
        "Selecciona una cotización para ver detalles:",
        [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in df.iterrows()]
    )
    cot_id = int(seleccion.split(" - ")[0])
    cot = df[df["id"] == cot_id].iloc[0]

    st.write(f"**Cliente:** {cot['cliente']}")
    st.write(f"**Proveedor Asignado:** {cot['proveedor_asignado']}")
    st.write(f"**Origen:** {cot['origen']}")
    st.write(f"**Destino:** {cot['destino']}")
    st.write(f"**Tipo de unidad:** {cot['tipo_unidad']}")
    st.write(f"**Descripción:** {cot['descripcion_paquete']}")
    st.write(f"**Precio total:** ${cot['precio_total']:,.2f}")
    st.write(f"**Fecha de creación:** {cot['fecha']}")

    st.markdown("---")
    if st.button("📄 Generar y Descargar PDF"):
        datos_pdf = {
            "cliente": cot['cliente'],
            "proveedor_asignado": cot['proveedor_asignado'],  # interno
            "origen": cot['origen'],
            "destino": cot['destino'],
            "tipo_unidad": cot['tipo_unidad'],
            "peso_kg": cot.get('peso_kg', 0),
            "descripcion_paquete": cot['descripcion_paquete'],
            "precio_total": cot['precio_total'],
            "fecha": cot['fecha'],
            "cotizacion_id": cot['cotizacion_id']
        }

        nombre_pdf = f"cotizacion_{cot['cotizacion_id']}.pdf"
        ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)

        with open(ruta_pdf, "rb") as f:
            st.download_button(
                label="📥 Descargar PDF",
                data=f,
                file_name=nombre_pdf,
                mime="application/pdf"
            )

    st.markdown("---")
    correo_cliente = st.text_input("Correo del cliente")
    if st.button("✉️ Enviar PDF por correo"):
        if not correo_cliente.strip():
            st.warning("Debes ingresar un correo válido.")
        else:
            # PDF de cara al cliente (sin proveedor)
            datos_pdf = {
                "cliente": cot['cliente'],
                "proveedor_asignado": "",  # oculto
                "origen": cot['origen'],
                "destino": cot['destino'],
                "tipo_unidad": cot['tipo_unidad'],
                "peso_kg": cot.get('peso_kg', 0),
                "descripcion_paquete": cot['descripcion_paquete'],
                "precio_total": cot['precio_total'],
                "fecha": cot['fecha'],
                "cotizacion_id": cot['cotizacion_id']
            }
            nombre_pdf = f"cotizacion_{cot['cotizacion_id']}.pdf"
            ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)

            asunto = "📦 Cotización Asignada - Eon Logistics"
            cuerpo = (f"Hola {cot['cliente']},\n\n"
                      "Adjunto encontrarás la cotización asignada con todos los detalles.\n\n"
                      "Gracias por confiar en Eon Logistics.")

            exito = enviar_email(correo_cliente, asunto, cuerpo, ruta_pdf)
            if exito:
                st.success(f"Correo enviado correctamente a {correo_cliente}.")
                # opcional: marcar en tránsito tras enviar
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE cotizaciones SET estatus = 'En tránsito' WHERE id = ?", (cot_id,))
                conn.commit()
                conn.close()
            else:
                st.error("❌ No se pudo enviar el correo. Verifica la configuración.")

# -------------------------------
# UI: Live tracking (control tower)
# -------------------------------
def live_tracking():
    st.subheader("🚦 EON Live Tracking - Control Tower")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cotizacion_id, cliente, origen, destino, proveedor_asignado, estatus, fecha
        FROM cotizaciones
        ORDER BY fecha DESC
    """, conn)
    conn.close()

    if df.empty:
        st.info("No hay movimientos registrados.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        filtro_estatus = st.selectbox("Filtrar por Estatus", ["Todos"] + df["estatus"].dropna().unique().tolist())
    with col2:
        filtro_proveedor = st.selectbox("Filtrar por Proveedor", ["Todos"] + df["proveedor_asignado"].fillna("No Asignado").unique().tolist())
    with col3:
        filtro_cliente = st.selectbox("Filtrar por Cliente", ["Todos"] + df["cliente"].dropna().unique().tolist())

    dfv = df.copy()
    if filtro_estatus != "Todos":
        dfv = dfv[dfv["estatus"] == filtro_estatus]
    if filtro_proveedor != "Todos":
        dfv = dfv[dfv["proveedor_asignado"].fillna("No Asignado") == filtro_proveedor]
    if filtro_cliente != "Todos":
        dfv = dfv[dfv["cliente"] == filtro_cliente]

    st.dataframe(dfv, use_container_width=True)

    seleccion = st.selectbox(
        "Selecciona una cotización para actualizar estatus:",
        [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in dfv.iterrows()]
    )
    cot_id = int(seleccion.split(" - ")[0])

    nuevo_estatus = st.selectbox("Nuevo estatus:", ["Pendiente por asignar", "Asignado", "En tránsito", "Entregado"])
    if st.button("Actualizar Estatus"):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE cotizaciones SET estatus = ? WHERE id = ?", (nuevo_estatus, cot_id))
        conn.commit()
        conn.close()
        st.success(f"Estatus de la cotización ID {cot_id} actualizado a '{nuevo_estatus}'.")
        st.rerun()

# -------------------------------
# UI: Dashboard KPI / Visual / Alertas
# -------------------------------
def dashboard_kpi():
    st.subheader("📊 EON Logistics - Dashboard KPI")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cliente, proveedor_asignado, estatus, fecha, precio_total
        FROM cotizaciones
        ORDER BY fecha DESC
    """, conn)
    conn.close()

    if df.empty:
        st.info("No hay datos aún.")
        return

    fechas = pd.to_datetime(df["fecha"])
    fecha_inicio = st.date_input("Desde", fechas.min().date())
    fecha_fin = st.date_input("Hasta", fechas.max().date())

    df = df[(fechas >= pd.to_datetime(fecha_inicio)) & (fechas <= pd.to_datetime(fecha_fin))]

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total Movimientos", len(df))
    col2.metric("🚚 En Proceso", len(df[df["estatus"].isin(["En tránsito", "Asignado"])]))
    col3.metric("⏳ Pendientes", len(df[df["estatus"] == "Pendiente por asignar"]))

    st.markdown("### 📈 Estado de Movimientos")
    estatus_count = df["estatus"].value_counts().reset_index()
    estatus_count.columns = ["Estatus", "Cantidad"]
    st.bar_chart(estatus_count.set_index("Estatus"))

    st.markdown("### 🧑‍💼 Top Clientes por Movimientos")
    top_clientes = df["cliente"].value_counts().head(5)
    st.dataframe(top_clientes)

    st.metric("💰 Ingreso Total (MXN)", f"${(df['precio_total'].fillna(0).sum()):,.2f}")

def visualizaciones_avanzadas():
    st.subheader("📊 Visualizaciones Avanzadas EON Logistics")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cliente, proveedor_asignado, estatus, origen, destino, fecha
        FROM cotizaciones
    """, conn)
    conn.close()

    if df.empty:
        st.info("No hay datos aún.")
        return

    # Pie Proveedor
    st.markdown("### 🥧 Distribución de Movimientos por Proveedor")
    proveedores_count = df["proveedor_asignado"].fillna("No Asignado").value_counts()
    st.plotly_chart({
        "data": [{
            "labels": proveedores_count.index.tolist(),
            "values": proveedores_count.values.tolist(),
            "type": "pie"
        }],
        "layout": {"margin": {"t": 0, "b": 0, "l": 0, "r": 0}}
    })

    # Heatmap simple de rutas (barra)
    st.markdown("### 🌍 Rutas (Origen → Destino)")
    df["ruta"] = df["origen"].fillna("") + " → " + df["destino"].fillna("")
    rutas_count = df["ruta"].value_counts().reset_index()
    rutas_count.columns = ["Ruta", "Cantidad"]
    st.bar_chart(rutas_count.set_index("Ruta"))

    # Tendencia semanal
    st.markdown("### 📆 Movimientos por Semana")
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["Semana"] = df["fecha"].dt.to_period('W').astype(str)
    semana_count = df["Semana"].value_counts().sort_index()
    st.line_chart(semana_count)

def dashboard_alertas():
    st.subheader("🚨 EON Control Tower - Alertas en Tiempo Real")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id, cotizacion_id, cliente, proveedor_asignado, estatus, fecha
        FROM cotizaciones
    """, conn)
    conn.close()

    if df.empty:
        st.info("No hay datos aún.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])
    hoy = datetime.now().date()
    hace_2_dias = hoy - timedelta(days=2)

    col1, col2, col3 = st.columns(3)
    sin_proveedor = df[df["proveedor_asignado"].isnull() | (df["proveedor_asignado"] == "")]
    col1.metric("⚠️ Sin Proveedor", len(sin_proveedor))

    en_transito_retrasados = df[(df["estatus"] == "En tránsito") & (df["fecha"].dt.date <= hace_2_dias)]
    col2.metric("🚚 Posibles Retrasos", len(en_transito_retrasados))

    entregados_hoy = df[(df["estatus"] == "Entregado") & (df["fecha"].dt.date == hoy)]
    col3.metric("✅ Entregados Hoy", len(entregados_hoy))

    st.markdown("### 📋 Detalle de Alertas Activas")
    df_alertas = pd.concat([sin_proveedor, en_transito_retrasados])
    st.dataframe(df_alertas, use_container_width=True)

    st.markdown("### 🔍 Filtros")
    filtro_estatus = st.selectbox("Estatus", ["Todos"] + df["estatus"].dropna().unique().tolist())
    filtro_proveedor = st.selectbox("Proveedor", ["Todos"] + df["proveedor_asignado"].fillna("No Asignado").unique().tolist())

    dfv = df.copy()
    if filtro_estatus != "Todos":
        dfv = dfv[dfv["estatus"] == filtro_estatus]
    if filtro_proveedor != "Todos":
        dfv = dfv[dfv["proveedor_asignado"].fillna("No Asignado") == filtro_proveedor]
    st.dataframe(dfv, use_container_width=True)

# ---------------------
# UI: Pricing
# ---------------------
def pricing_module():
    st.subheader("📈 Sistema de Pricing - EON Logistics")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # --- Tarifas Base ---
    st.markdown("### 🚚 Tarifas Base por Ruta")
    with st.form("form_tarifa"):
        origen = st.text_input("Origen")
        destino = st.text_input("Destino")
        tarifa_base = st.number_input(
            "Tarifa Base (MXN por kg o unidad base de tu modelo)",
            min_value=0.0, value=0.0
        )
        sent = st.form_submit_button("Agregar / Actualizar Tarifa")
        if sent:
            c.execute("""
                INSERT INTO tarifas (origen, destino, tarifa_base)
                VALUES (?, ?, ?)
                ON CONFLICT(origen, destino) DO UPDATE SET tarifa_base=excluded.tarifa_base
            """, (origen, destino, tarifa_base))
            conn.commit()
            st.success(f"Tarifa {origen} → {destino} guardada.")
            st.rerun()

    st.dataframe(
        pd.read_sql_query("SELECT origen, destino, tarifa_base FROM tarifas", conn),
        use_container_width=True
    )
    st.markdown("---")

    # --- Márgenes ---
    st.markdown("### 💰 Márgenes de Utilidad")
    with st.form("form_margen"):
        criterio = st.selectbox("Criterio", ["unidad", "general"])  # usa 'unidad' o 'general'
        valor = st.text_input("Valor (p.ej. 'Camión 3.5t' o 'General')")
        margen = st.number_input("Margen (%)", min_value=0.0, value=0.0)
        sent2 = st.form_submit_button("Agregar / Actualizar Margen")
        if sent2:
            c.execute("""
                INSERT INTO margenes (criterio, valor, margen_porcentaje)
                VALUES (?, ?, ?)
                ON CONFLICT(criterio, valor) DO UPDATE SET margen_porcentaje=excluded.margen_porcentaje
            """, (criterio, valor, margen))
            conn.commit()
            st.success(f"Margen para {criterio}:{valor} guardado.")
            st.rerun()

    st.dataframe(
        pd.read_sql_query("SELECT criterio, valor, margen_porcentaje FROM margenes", conn),
        use_container_width=True
    )
    st.markdown("---")

    # --- Márgenes por Peso ---
    st.markdown("### ⚖️ Márgenes por Peso (rangos)")
    with st.form("form_margen_peso"):
        rmin = st.number_input("Rango mínimo (kg)", min_value=0.0, value=0.0)
        rmax = st.number_input("Rango máximo (kg)", min_value=0.0, value=0.0)
        mp = st.number_input("Margen (%)", min_value=0.0, value=0.0)
        sent3 = st.form_submit_button("Agregar rango")
        if sent3:
            c.execute("""
                INSERT INTO margenes_peso (rango_min, rango_max, margen_porcentaje)
                VALUES (?, ?, ?)
            """, (rmin, rmax, mp))
            conn.commit()
            st.success("Rango de margen por peso agregado.")
            st.rerun()

    st.dataframe(
        pd.read_sql_query("SELECT rango_min, rango_max, margen_porcentaje FROM margenes_peso", conn),
        use_container_width=True
    )
    conn.close()

# ---------------------
# UI: Cotizar vía DHL (con session_state)
# ---------------------
def cotizar_dhl_api_ui():
    st.subheader("🚚 Cotizar vía API (DHL)")

    # --- Inputs ---
    colA, colB = st.columns(2)
    with colA:
        origen_cp = st.text_input("CP Origen", "64000")
        origen_ciudad = st.text_input("Ciudad Origen", "Monterrey")
        peso = st.number_input("Peso (kg)", min_value=0.1, value=5.0)
    with colB:
        destino_cp = st.text_input("CP Destino", "01000")
        destino_ciudad = st.text_input("Ciudad Destino", "Ciudad de México")
        dim_str = st.text_input("Dimensiones LxAxH (cm)", "10x10x10")

    # Parseo seguro de dimensiones
    largo, ancho, alto = 10.0, 10.0, 10.0
    try:
        l, a, h = dim_str.lower().replace(" ", "").split("x")
        largo, ancho, alto = float(l), float(a), float(h)
    except Exception:
        pass

    # --- Acción: cotizar ---
    if st.button("🔎 Cotizar DHL"):
        try:
            res = cotizar_dhl(
                origen_cp, destino_cp, peso,
                largo=largo, ancho=ancho, alto=alto,
                origin_city=origen_ciudad, dest_city=destino_ciudad,
                is_customs_declarable=False
            )
            dhl_json = res["json"]
            ofertas = normalizar_ofertas_dhl(dhl_json)

            # Persistimos en session_state para que no se "pierda" al hacer clics
            st.session_state["dhl_inputs"] = {
                "origen_cp": origen_cp,
                "destino_cp": destino_cp,
                "peso": peso,
                "largo": largo,
                "ancho": ancho,
                "alto": alto,
                "origen_ciudad": origen_ciudad,
                "destino_ciudad": destino_ciudad,
            }
            st.session_state["dhl_raw_json"] = dhl_json
            st.session_state["dhl_ofertas"] = ofertas or []

            if not ofertas:
                st.warning("DHL no devolvió precios utilizables para estos parámetros.")
                with st.expander("Ver respuesta completa (debug)"):
                    st.code(dhl_json, language="json")
            else:
                st.success(f"{len(ofertas)} opción(es) encontradas.")
        except requests.HTTPError as e:
            st.error(f"HTTPError DHL: {e}")
            try:
                st.code(e.response.text, language="json")
            except Exception:
                pass
        except Exception as e:
            st.error(f"Error al cotizar DHL: {e}")

    # --- Render de resultados si existen en session_state ---
    ofertas = st.session_state.get("dhl_ofertas", [])
    if ofertas:
        # Lista expandible de ofertas
        for of in ofertas:
            titulo = f"{of['productName']} — {of['totalPrice']} {of['currency']} | Transit days (estimado): {of.get('etd_days', 'N/D')}"
            with st.expander(titulo, expanded=False):
                raw = of.get("raw", of)  # si no guardaste raw, muestra dict simple
                st.json(raw)

        st.markdown("### Elige oferta para registrar en la BD")
        idx = st.selectbox(
            "Oferta",
            options=list(range(len(ofertas))),
            format_func=lambda i: f"{ofertas[i]['productName']} - {ofertas[i]['totalPrice']} {ofertas[i]['currency']}"
        )

        if st.button("💾 Registrar oferta DHL"):
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS ofertas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        id_cotizacion INTEGER,
                        proveedor TEXT,
                        precio_ofertado REAL,
                        mensaje TEXT,
                        fecha TEXT
                    )
                """)
                df_cots = pd.read_sql_query("""
                    SELECT id, cliente, origen, destino, precio_total, fecha
                    FROM cotizaciones
                    ORDER BY fecha DESC
                """, conn)

                if df_cots.empty:
                    st.warning("No hay cotizaciones en la base para asociar esta oferta.")
                else:
                    # Por ahora: asociar a la más reciente
                    cot_id = int(df_cots.iloc[0]["id"])
                    sel = ofertas[idx]
                    msg = f"DHL {sel['productName']} • ETA: {sel.get('etd_days', 'N/D')}"
                    c.execute("""
                        INSERT INTO ofertas (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha)
                        VALUES (?, ?, ?, ?, DATE('now'))
                    """, (cot_id, "DHL", float(sel["totalPrice"]), msg))
                    conn.commit()
                    st.success(f"Oferta de DHL registrada en la cotización #{cot_id}.")
            except Exception as ex:
                st.error(f"No se pudo registrar la oferta: {ex}")
            finally:
                try:
                    conn.close()
                except:
                    pass

# --------------------------------
# SideBar y enrutamiento de páginas
# --------------------------------
st.sidebar.title("EON Operations Portal")
menu = st.sidebar.radio(
    "Navegación",
    [
        "Dashboard", "Cotizaciones", "Pricing", "Proveedores", "Clientes",
        "Seguimiento", "Live Tracking", "Dashboard KPI",
        "Visualizaciones Avanzadas", "Alertas en Tiempo Real", "Pricing Inteligente"
    ]
)

if menu == "Dashboard":
    st.title("📊 Dashboard General")
    st.write("Resumen de movimientos actuales, programados y entregados recientemente.")

elif menu == "Cotizaciones":
    st.title("💼 Cotizaciones")
    opcion = st.selectbox("Selecciona una opción", ["Nueva Cotización (Manual)", "Cotizar vía API (DHL)", "Pendientes por Asignar", "Cotizaciones Asignadas"])

    if opcion == "Nueva Cotización (Manual)":
        nueva_cotizacion_manual()
    elif opcion == "Cotizar vía API (DHL)":
        cotizar_dhl_api_ui()
    elif opcion == "Pendientes por Asignar":
        cotizaciones_pendientes()
    elif opcion == "Cotizaciones Asignadas":
        cotizaciones_asignadas()

elif menu == "Pricing":
    st.title("📈 Pricing EON")
    pricing_module()

elif menu == "Proveedores":
    st.title("🚛 Gestión de Proveedores")
    st.write("Alta, baja y ofertas recibidas.")

elif menu == "Clientes":
    st.title("🧑‍💼 Gestión de Clientes")
    st.write("Alta de clientes, historial de cotizaciones.")

elif menu == "Seguimiento":
    st.title("🔎 Seguimiento de Envíos")
    st.write("Buscar estado de movimientos por Cotización ID.")

elif menu == "Live Tracking":
    live_tracking()

elif menu == "Dashboard KPI":
    dashboard_kpi()

elif menu == "Visualizaciones Avanzadas":
    visualizaciones_avanzadas()

elif menu == "Alertas en Tiempo Real":
    dashboard_alertas()

elif menu == "Pricing Inteligente":
    pricing_module()