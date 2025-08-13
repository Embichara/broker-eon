# EON OPS DASHBOARD - Streamlit Structure (Base Multipage)

import requests
import streamlit as st
import sqlite3
from datetime import date
import uuid
import pandas as pd
from fpdf import FPDF
import os
import smtplib
from email.message import EmailMessage
import os
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from carriers.dhl_client import cotizar_dhl, normalizar_ofertas_dhl

def cotizar_dhl_api():
    import pandas as pd
    import streamlit as st
    from carriers.dhl_client import dhl_rate_request, parse_rates_to_rows
    st.subheader("🟡 Cotizar vía API (DHL Express)")

    col1, col2 = st.columns(2)
    with col1:
        origen_pais = st.text_input("País Origen (ISO-2)", value="MX")
        origen_cp = st.text_input("C.P. Origen", value="64000")
        peso = st.number_input("Peso (kg)", min_value=0.1, value=5.0)
        largo = st.number_input("Largo (cm)", min_value=1.0, value=10.0)
    with col2:
        destino_pais = st.text_input("País Destino (ISO-2)", value="MX")
        destino_cp = st.text_input("C.P. Destino", value="03100")
        ancho = st.number_input("Ancho (cm)", min_value=1.0, value=10.0)
        alto = st.number_input("Alto (cm)", min_value=1.0, value=10.0)

    if st.button("📡 Consultar tarifas DHL"):
        try:
            data = dhl_rate_request(
                origin_country=origen_pais.strip().upper(),
                origin_postal=origen_cp.strip(),
                dest_country=destino_pais.strip().upper(),
                dest_postal=destino_cp.strip(),
                weight_kg=peso,
                length_cm=largo, width_cm=ancho, height_cm=alto
            )
            rows = parse_rates_to_rows(data)
            if not rows:
                st.warning("DHL respondió sin tarifas. Verifica datos o credenciales.")
                st.caption("Respuesta recibida (debug):")
                st.code(data, language="json")
            else:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
                with st.expander("Ver JSON completo (debug)"):
                    st.code(data, language="json")
        except requests.HTTPError as e:
            st.error(f"HTTPError DHL: {e}")
            try:
                st.code(e.response.text, language="json")
            except Exception:
                pass
        except Exception as ex:
            st.error(f"Error inesperado: {ex}")

def pricing_module():
    st.subheader("📈 Sistema de Pricing - EON Logistics")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Crear tabla de tarifas si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tarifas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origen TEXT,
            destino TEXT,
            tarifa_base REAL
        )
    """)

    # Crear tabla de márgenes si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS margenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criterio TEXT,  -- cliente / unidad / general
            valor TEXT,
            margen_porcentaje REAL
        )
    """)

    conn.commit()

    # --- Sección de Tarifas Base ---
    st.markdown("### 🚚 Tarifas Base por Ruta")
    with st.form("nueva_tarifa"):
        origen = st.text_input("Origen")
        destino = st.text_input("Destino")
        tarifa_base = st.number_input("Tarifa Base (MXN)", min_value=1.0)
        submitted = st.form_submit_button("Agregar / Actualizar Tarifa")

        if submitted:
            cursor.execute("""
                INSERT INTO tarifas (origen, destino, tarifa_base)
                VALUES (?, ?, ?)
                ON CONFLICT(origen, destino) DO UPDATE SET tarifa_base=excluded.tarifa_base
            """, (origen, destino, tarifa_base))
            conn.commit()
            st.success(f"Tarifa para {origen} → {destino} actualizada: ${tarifa_base}")

    tarifas_df = pd.read_sql_query("SELECT * FROM tarifas", conn)
    st.dataframe(tarifas_df)

    st.markdown("---")

    # --- Sección de Márgenes ---
    st.markdown("### 💰 Márgenes de Utilidad")
    with st.form("nuevo_margen"):
        criterio = st.selectbox("Criterio", ["cliente", "unidad", "general"])
        valor = st.text_input("Valor (nombre del cliente / tipo de unidad / General)")
        margen = st.number_input("Margen (%)", min_value=0.0, max_value=100.0)
        submitted_margen = st.form_submit_button("Agregar / Actualizar Margen")

        if submitted_margen:
            cursor.execute("""
                INSERT INTO margenes (criterio, valor, margen_porcentaje)
                VALUES (?, ?, ?)
                ON CONFLICT(criterio, valor) DO UPDATE SET margen_porcentaje=excluded.margen_porcentaje
            """, (criterio, valor, margen))
            conn.commit()
            st.success(f"Margen {margen}% aplicado a {valor}")

    margenes_df = pd.read_sql_query("SELECT * FROM margenes", conn)
    st.dataframe(margenes_df)

    conn.close()

def dashboard_alertas():
    st.subheader("🚨 EON Control Tower - Alertas en Tiempo Real")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cotizacion_id, cliente, proveedor_asignado, estatus, fecha
        FROM cotizaciones
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["fecha"] = pd.to_datetime(df["fecha"])

    hoy = datetime.now().date()
    hace_2_dias = hoy - timedelta(days=2)

    col1, col2, col3 = st.columns(3)

    # Alertas Críticas - Sin Proveedor
    sin_proveedor = df[df["proveedor_asignado"].isnull() | (df["proveedor_asignado"] == "")]
    col1.metric("⚠️ Sin Proveedor", len(sin_proveedor))

    # Posibles Retrasos - En tránsito sin actualización
    en_transito_retrasados = df[(df["estatus"] == "En tránsito") & (df["fecha"].dt.date <= hace_2_dias)]
    col2.metric("🚚 Posibles Retrasos", len(en_transito_retrasados))

    # Movimientos Entregados Hoy
    entregados_hoy = df[(df["estatus"] == "Entregado") & (df["fecha"].dt.date == hoy)]
    col3.metric("✅ Entregados Hoy", len(entregados_hoy))

    st.markdown("### 📋 Detalle de Alertas Activas")

    # Tabla de Detalle
    df_alertas = pd.concat([sin_proveedor, en_transito_retrasados])
    st.dataframe(df_alertas, use_container_width=True)

    # Filtros rápidos
    st.markdown("### 🔍 Filtros de Búsqueda")
    filtro_estatus = st.selectbox("Filtrar por Estatus", ["Todos"] + df["estatus"].unique().tolist())
    filtro_proveedor = st.selectbox("Filtrar por Proveedor", ["Todos"] + df["proveedor_asignado"].dropna().unique().tolist())

    df_filtro = df.copy()
    if filtro_estatus != "Todos":
        df_filtro = df_filtro[df_filtro["estatus"] == filtro_estatus]
    if filtro_proveedor != "Todos":
        df_filtro = df_filtro[df_filtro["proveedor_asignado"] == filtro_proveedor]

    st.dataframe(df_filtro, use_container_width=True)

def visualizaciones_avanzadas():
    st.subheader("📊 Visualizaciones Avanzadas EON Logistics")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cliente, proveedor_asignado, estatus, origen, destino, fecha
        FROM cotizaciones
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Pie Chart - Movimientos por Proveedor
    st.markdown("### 🥧 Distribución de Movimientos por Proveedor")
    proveedores_count = df["proveedor_asignado"].fillna("No Asignado").value_counts()
    st.plotly_chart({
        "data": [{
            "labels": proveedores_count.index,
            "values": proveedores_count.values,
            "type": "pie"
        }],
        "layout": {"margin": {"t": 0, "b": 0, "l": 0, "r": 0}}
    })

    # Heatmap de Rutas
    st.markdown("### 🌍 Heatmap de Rutas (Origen → Destino)")
    df["ruta"] = df["origen"] + " → " + df["destino"]
    rutas_count = df["ruta"].value_counts().reset_index()
    rutas_count.columns = ["Ruta", "Cantidad"]
    st.bar_chart(rutas_count.set_index("Ruta"))

    # Tendencia Semanal de Movimientos
    st.markdown("### 📆 Movimientos por Semana")
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["Semana"] = df["fecha"].dt.to_period('W').astype(str)
    semana_count = df["Semana"].value_counts().sort_index()
    st.line_chart(semana_count)

def dashboard_kpi():
    st.subheader("📊 EON Logistics - Dashboard KPI")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cliente, proveedor_asignado, estatus, fecha, precio_total
        FROM cotizaciones
        ORDER BY fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Filtros de Fecha
    fechas = pd.to_datetime(df["fecha"])
    fecha_inicio = st.date_input("Desde", fechas.min().date())
    fecha_fin = st.date_input("Hasta", fechas.max().date())

    df = df[(fechas >= pd.to_datetime(fecha_inicio)) & (fechas <= pd.to_datetime(fecha_fin))]

    # KPIs Principales
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📦 Total Movimientos", len(df))
    with col2:
        st.metric("🚚 En Proceso", len(df[df["estatus"].isin(["En tránsito", "Asignado"])]))
    with col3:
        st.metric("⏳ Pendientes", len(df[df["estatus"] == "Pendiente por asignar"]))

    # Gráfica de Estatus
    st.markdown("### 📈 Estado de Movimientos")
    estatus_count = df["estatus"].value_counts().reset_index()
    estatus_count.columns = ["Estatus", "Cantidad"]

    st.bar_chart(estatus_count.set_index("Estatus"))

    # Top Clientes (Movimientos)
    st.markdown("### 🧑‍💼 Top Clientes por Movimientos")
    top_clientes = df["cliente"].value_counts().head(5)
    st.dataframe(top_clientes)

    # Suma Total de Ventas
    st.metric("💰 Ingreso Total (MXN)", f"${df['precio_total'].sum():,.2f}")

def enviar_email(destinatario, asunto, cuerpo, archivo_pdf=None):
    EMAIL = os.getenv("EMAIL")
    PASSWORD = os.getenv("PASSWORD")

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

def generar_pdf_cotizacion(datos, nombre_archivo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, "Cotización de Envío - Eon Logistics", ln=True, align="C")
    pdf.ln(10)

    pdf.cell(0, 10, f"Cliente: {datos['cliente']}", ln=True)
    if datos.get("proveedor_asignado") != "":
        pdf.cell(0, 10, f"Proveedor Asignado: {datos['proveedor_asignado']}", ln=True)
    pdf.cell(0, 10, f"Origen: {datos['origen']}", ln=True)
    pdf.cell(0, 10, f"Destino: {datos['destino']}", ln=True)
    pdf.cell(0, 10, f"Tipo de unidad: {datos['tipo_unidad']}", ln=True)
    pdf.cell(0, 10, f"Peso: {datos['peso_kg']} kg", ln=True)
    pdf.multi_cell(0, 10, f"Descripción: {datos['descripcion_paquete']}")
    pdf.cell(0, 10, f"Precio total: ${datos['precio_total']:,.2f}", ln=True)
    pdf.cell(0, 10, f"Fecha: {datos['fecha']}", ln=True)

    # 🔥 Agregar link de seguimiento
    seguimiento_url = f"https://eonlogisticgroup.com/estatus/{datos['cotizacion_id']}"
    pdf.ln(10)
    pdf.set_text_color(0, 0, 255)  # Azul para el link
    pdf.cell(0, 10, f"Seguimiento en línea: {seguimiento_url}", ln=True, link=seguimiento_url)
    pdf.set_text_color(0, 0, 0)  # Regresar a negro

    # Crear carpeta si no existe
    if not os.path.exists("../app/cotizaciones_pdf"):
        os.makedirs("../app/cotizaciones_pdf")

    ruta_pdf = f"../app/cotizaciones_pdf/{nombre_archivo}"
    pdf.output(ruta_pdf)
    return ruta_pdf

def nueva_cotizacion_manual():
    st.subheader("\U0001F4DD Nueva Cotización (Manual)")

    origen = st.text_input("Origen")
    destino = st.text_input("Destino")
    tipo_unidad = st.selectbox("Tipo de unidad", ["Camioneta", "Camión 3.5t", "Tráiler", "Caja Seca", "Caja Refrigerada"])
    peso = st.number_input("Peso del paquete (kg)", min_value=0.1)
    descripcion = st.text_area("Descripción del paquete")
    cliente = st.text_input("Nombre del cliente")
    # precio_total = st.number_input("Precio total (MXN)", min_value=1.0)

    if not origen or not destino or not cliente or peso <= 0:
        st.warning("Por favor llena todos los campos correctamente.")
        return

    if st.button("💾 Guardar cotización"):
        cotizacion_id = str(uuid.uuid4())[:8]
        estatus_url = f"https://eonlogisticgroup.com/estatus/{cotizacion_id}"

        DB_PATH = os.path.abspath("eon.db")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Buscar tarifa base por ruta
        cursor.execute("""
            SELECT tarifa_base FROM tarifas WHERE origen = ? AND destino = ?
        """, (origen, destino))
        resultado_tarifa = cursor.fetchone()

        if not resultado_tarifa:
            st.error("No se encontró una tarifa base para esta ruta. Configúrala en el módulo de Pricing.")
            conn.close()
            return

        tarifa_base = resultado_tarifa[0]

        if resultado_tarifa:
            tarifa_base = resultado_tarifa[0]
        else:
            st.error("No se encontró una tarifa base para esta ruta.")
            conn.close()
            return

        cursor.execute("""
            SELECT margen_porcentaje FROM margenes WHERE criterio = 'unidad' AND valor = ?
        """, (tipo_unidad,))
        resultado_margen_unidad = cursor.fetchone()

        if not resultado_margen_unidad:
            st.error(f"No se encontró un margen de utilidad para la unidad: {tipo_unidad}. Configúralo en el módulo de Pricing.")
            conn.close()
            return

        margen_unidad = resultado_margen_unidad[0]

        # Buscar margen por peso (rango)
        cursor.execute("""
            SELECT margen_porcentaje FROM margenes_peso WHERE ? BETWEEN rango_min AND rango_max
        """, (peso,))
        resultado_margen_peso = cursor.fetchone()

        if not resultado_margen_peso:
            st.error(f"No se encontró un margen de utilidad para el peso: {peso} kg. Configúralo en el módulo de Pricing.")
            conn.close()
            return

        margen_peso = resultado_margen_peso[0]

        # Cálculo del precio total con ambos márgenes
        precio_sin_margen = tarifa_base * peso
        precio_total = precio_sin_margen * (1 + margen_unidad / 100) * (1 + margen_peso / 100)

        # Insertar cotización en la base de datos
        cursor.execute("""
            INSERT INTO cotizaciones (
                cotizacion_id, cliente, origen, destino, distancia_km, peso_kg,
                descripcion_paquete, tipo_unidad, precio_total, fecha, estatus_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cotizacion_id, cliente, origen, destino, 0, peso,
            descripcion, tipo_unidad, precio_total, str(date.today()), estatus_url
        ))

        # Obtener el ID de la cotización recién creada
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cotizaciones WHERE cotizacion_id = ?", (cotizacion_id,))
        resultado_cotizacion = cursor.fetchone()
        id_cotizacion = resultado_cotizacion[0]

        # Buscar proveedores compatibles
        cursor.execute("""
            SELECT proveedor, factor_precio FROM proveedores_rutas
            WHERE origen = ? AND destino = ? AND tipo_unidad = ?
        """, (origen, destino, tipo_unidad))
        proveedores = cursor.fetchall()

        # Insertar ofertas automáticas
        from datetime import datetime
        fecha_actual = str(datetime.now().date())

        for proveedor, factor_precio in proveedores:
            precio_ofertado = precio_total * factor_precio
            mensaje = f"Oferta automática generada para {proveedor}"
            cursor.execute("""
                INSERT INTO ofertas (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha)
                VALUES (?, ?, ?, ?, ?)
            """, (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha_actual))

        conn.commit()
        conn.close()

        st.success(f"Se generaron {len(proveedores)} ofertas automáticas.")

        conn.commit()
        conn.close()

        st.success(f"Cotización generada automáticamente: ${precio_total:,.2f} MXN")
        st.write(f"Estatus URL: {estatus_url}")

def cotizaciones_pendientes():
    st.subheader("📋 Cotizaciones Pendientes por Asignar")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cotizacion_id, cliente, origen, destino, tipo_unidad, descripcion_paquete, precio_total, fecha, proveedor_asignado
        FROM cotizaciones
        ORDER BY fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df_pendientes = df[df["proveedor_asignado"].isnull() | (df["proveedor_asignado"] == "")]

    if df_pendientes.empty:
        st.info("No hay cotizaciones pendientes por asignar.")
    else:
        st.dataframe(df_pendientes, use_container_width=True)

        seleccion = st.selectbox(
            "Selecciona una cotización para ver detalles:",
            [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in df_pendientes.iterrows()]
        )

        cotizacion_id = int(seleccion.split(" - ")[0])
        cotizacion_seleccionada = df_pendientes[df_pendientes["id"] == cotizacion_id].iloc[0]

        st.write(f"**Cliente:** {cotizacion_seleccionada['cliente']}")
        st.write(f"**Origen:** {cotizacion_seleccionada['origen']}")
        st.write(f"**Destino:** {cotizacion_seleccionada['destino']}")
        st.write(f"**Tipo de unidad:** {cotizacion_seleccionada['tipo_unidad']}")
        st.write(f"**Descripción:** {cotizacion_seleccionada['descripcion_paquete']}")
        st.write(f"**Precio total:** ${cotizacion_seleccionada['precio_total']:,.2f}")
        st.write(f"**Fecha de creación:** {cotizacion_seleccionada['fecha']}")

        st.markdown("---")
        st.subheader("Asignar Proveedor")

        proveedor = st.text_input("Nombre del Proveedor")
        if st.button("✅ Asignar Proveedor"):
            if proveedor.strip() == "":
                st.warning("Debes ingresar el nombre de un proveedor.")
            else:
                DB_PATH = os.path.abspath("eon.db")
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE cotizaciones
                    SET proveedor_asignado = ?, estatus = 'Asignado'
                    WHERE id = ?
                """, (proveedor, cotizacion_id))
                conn.commit()
                conn.close()

                st.success(f"Proveedor '{proveedor}' asignado correctamente a la cotización ID {cotizacion_id}.")

                # 🔥 Automatización: Enviar PDF al cliente SIN mostrar proveedor
                DB_PATH = os.path.abspath("eon.db")
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT correo FROM usuarios WHERE nombre = ?", (cotizacion_seleccionada['cliente'],))
                resultado_cliente = cursor.fetchone()
                conn.close()

                if resultado_cliente:
                    correo_cliente = resultado_cliente[0]

                    # Generar PDF ocultando proveedor
                    datos_pdf = {
                        "cliente": cotizacion_seleccionada['cliente'],
                        "proveedor_asignado": "",  # No mostrar proveedor
                        "origen": cotizacion_seleccionada['origen'],
                        "destino": cotizacion_seleccionada['destino'],
                        "tipo_unidad": cotizacion_seleccionada['tipo_unidad'],
                        "peso_kg": cotizacion_seleccionada['peso_kg'] if 'peso_kg' in cotizacion_seleccionada else 0,
                        "descripcion_paquete": cotizacion_seleccionada['descripcion_paquete'],
                        "precio_total": cotizacion_seleccionada['precio_total'],
                        "fecha": cotizacion_seleccionada['fecha']
                    }

                    nombre_pdf = f"cotizacion_{cotizacion_seleccionada['cotizacion_id']}.pdf"
                    ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)

                    asunto = "📦 Cotización Asignada - Eon Logistics"
                    cuerpo = f"Hola {cotizacion_seleccionada['cliente']},\n\nTu cotización ha sido procesada.\nAdjunto encontrarás el PDF con los detalles.\n\nGracias por confiar en Eon Logistics."

                    exito = enviar_email(correo_cliente, asunto, cuerpo, ruta_pdf)

                    if exito:
                        st.success(f"Correo enviado correctamente a {correo_cliente}.")
                    else:
                        st.error("❌ No se pudo enviar el correo al cliente.")
                else:
                    st.warning("⚠️ No se encontró el correo del cliente.")

                st.rerun()

def cotizaciones_asignadas():
    st.subheader("📑 Cotizaciones Asignadas")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cotizacion_id, cliente, origen, destino, tipo_unidad, descripcion_paquete, precio_total, fecha, proveedor_asignado
        FROM cotizaciones
        WHERE proveedor_asignado IS NOT NULL AND proveedor_asignado != ''
        ORDER BY fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        st.info("No hay cotizaciones asignadas.")
    else:
        st.dataframe(df, use_container_width=True)

        seleccion = st.selectbox(
            "Selecciona una cotización para ver detalles:",
            [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in df.iterrows()]
        )

        cotizacion_id = int(seleccion.split(" - ")[0])
        cotizacion_seleccionada = df[df["id"] == cotizacion_id].iloc[0]

        st.write(f"**Cliente:** {cotizacion_seleccionada['cliente']}")
        st.write(f"**Proveedor Asignado:** {cotizacion_seleccionada['proveedor_asignado']}")
        st.write(f"**Origen:** {cotizacion_seleccionada['origen']}")
        st.write(f"**Destino:** {cotizacion_seleccionada['destino']}")
        st.write(f"**Tipo de unidad:** {cotizacion_seleccionada['tipo_unidad']}")
        st.write(f"**Descripción:** {cotizacion_seleccionada['descripcion_paquete']}")
        st.write(f"**Precio total:** ${cotizacion_seleccionada['precio_total']:,.2f}")
        st.write(f"**Fecha de creación:** {cotizacion_seleccionada['fecha']}")

        st.markdown("---")
        if st.button("📄 Generar y Descargar PDF"):
            datos_pdf = {
                "cliente": cotizacion_seleccionada['cliente'],
                "proveedor_asignado": cotizacion_seleccionada['proveedor_asignado'],
                "origen": cotizacion_seleccionada['origen'],
                "destino": cotizacion_seleccionada['destino'],
                "tipo_unidad": cotizacion_seleccionada['tipo_unidad'],
                "peso_kg": cotizacion_seleccionada['peso_kg'] if 'peso_kg' in cotizacion_seleccionada else 0,
                "descripcion_paquete": cotizacion_seleccionada['descripcion_paquete'],
                "precio_total": cotizacion_seleccionada['precio_total'],
                "fecha": cotizacion_seleccionada['fecha'],
                "cotizacion_id": cotizacion_seleccionada['cotizacion_id']
            }

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE cotizaciones SET estatus = 'En tránsito' WHERE id = ?", (cotizacion_id,))
            conn.commit()
            conn.close()

            # Actualizar estatus a 'En tránsito'
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE cotizaciones SET estatus = 'En tránsito' WHERE id = ?", (cotizacion_id,))
            conn.commit()
            conn.close()

            nombre_pdf = f"cotizacion_{cotizacion_seleccionada['cotizacion_id']}.pdf"
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
            if correo_cliente.strip() == "":
                st.warning("Debes ingresar un correo válido.")
            else:
                # Generar el PDF si no existe
                asunto = "📦 Cotización Asignada - Eon Logistics"
                cuerpo = f"Hola {cotizacion_seleccionada['cliente']},\n\nAdjunto encontrarás la cotización asignada con todos los detalles.\n\nGracias por confiar en Eon Logistics."

                datos_pdf = {
                    "cliente": cotizacion_seleccionada['cliente'],
                    "proveedor_asignado": "",  # No mostrar proveedor
                    "origen": cotizacion_seleccionada['origen'],
                    "destino": cotizacion_seleccionada['destino'],
                    "tipo_unidad": cotizacion_seleccionada['tipo_unidad'],
                    "peso_kg": cotizacion_seleccionada['peso_kg'] if 'peso_kg' in cotizacion_seleccionada else 0,
                    "descripcion_paquete": cotizacion_seleccionada['descripcion_paquete'],
                    "precio_total": cotizacion_seleccionada['precio_total'],
                    "fecha": cotizacion_seleccionada['fecha'],
                    "cotizacion_id": cotizacion_seleccionada['cotizacion_id']
                }

                nombre_pdf = f"cotizacion_{cotizacion_seleccionada['cotizacion_id']}.pdf"
                ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)  # <== Esto es clave
                exito = enviar_email(correo_cliente, asunto, cuerpo, ruta_pdf)

                if exito:
                    st.success(f"Correo enviado correctamente a {correo_cliente}.")
                    # Actualizar estatus a 'En tránsito'
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE cotizaciones SET estatus = 'En tránsito' WHERE id = ?", (cotizacion_id,))
                    conn.commit()
                    conn.close()
                else:
                    st.error("❌ No se pudo enviar el correo. Verifica la configuración.")

                nombre_pdf = f"cotizacion_{cotizacion_seleccionada['cotizacion_id']}.pdf"
                ruta_pdf = generar_pdf_cotizacion(datos_pdf, nombre_pdf)

                asunto = "📦 Cotización Asignada - Eon Logistics"
                cuerpo = f"Hola {cotizacion_seleccionada['cliente']},\n\nAdjunto encontrarás la cotización asignada con todos los detalles.\n\nGracias por confiar en Eon Logistics."
                
                exito = enviar_email(correo_cliente, asunto, cuerpo, ruta_pdf)
                
                if exito:
                    st.success(f"Correo enviado correctamente a {correo_cliente}.")
                else:
                    st.error("❌ No se pudo enviar el correo. Verifica la configuración.")

def live_tracking():
    st.subheader("🚦 EON Live Tracking - Control Tower")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT id, cotizacion_id, cliente, origen, destino, proveedor_asignado, estatus, fecha
        FROM cotizaciones
        ORDER BY fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Filtros rápidos
    col1, col2, col3 = st.columns(3)
    with col1:
        filtro_estatus = st.selectbox("Filtrar por Estatus", ["Todos"] + df["estatus"].unique().tolist())
    with col2:
        filtro_proveedor = st.selectbox("Filtrar por Proveedor", ["Todos"] + df["proveedor_asignado"].dropna().unique().tolist())
    with col3:
        filtro_cliente = st.selectbox("Filtrar por Cliente", ["Todos"] + df["cliente"].dropna().unique().tolist())

    # Aplicar filtros
    if filtro_estatus != "Todos":
        df = df[df["estatus"] == filtro_estatus]
    if filtro_proveedor != "Todos":
        df = df[df["proveedor_asignado"] == filtro_proveedor]
    if filtro_cliente != "Todos":
        df = df[df["cliente"] == filtro_cliente]

    st.dataframe(df, use_container_width=True)

    # Cambiar estatus de movimiento
    seleccion = st.selectbox(
        "Selecciona una cotización para actualizar estatus:",
        [f"{row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})" for _, row in df.iterrows()]
    )

    cotizacion_id = int(seleccion.split(" - ")[0])

    nuevo_estatus = st.selectbox("Nuevo estatus:", ["Pendiente por asignar", "Asignado", "En tránsito", "Entregado"])
    if st.button("Actualizar Estatus"):
        conn = sqlite3.connect(DB_PATH)  # <-- Ahora sí lee el archivo correcto
        cursor = conn.cursor()
        cursor.execute("UPDATE cotizaciones SET estatus = ? WHERE id = ?", (nuevo_estatus, cotizacion_id))
        conn.commit()
        conn.close()
        st.success(f"Estatus de la cotización ID {cotizacion_id} actualizado a '{nuevo_estatus}'.")
        st.rerun()

st.set_page_config(page_title="EON OPS Portal", page_icon="🚚", layout="wide")

st.sidebar.title("EON Operations Portal")
menu = st.sidebar.radio("Navegación", ["Dashboard", "Cotizaciones", "Pricing", "Proveedores", "Clientes", "Seguimiento", "Live Tracking", "Dashboard KPI", "Visualizaciones Avanzadas", "Alertas en Tiempo Real", "Pricing Inteligente"])

if menu == "Dashboard":
    st.title("📊 Dashboard General")
    st.write("Resumen de movimientos actuales, programados y entregados recientemente.")

elif menu == "Cotizaciones":
    st.title("💼 Cotizaciones")
    opcion = st.selectbox("Selecciona una opción", ["Nueva Cotización (Manual)", "Cotizar vía API (DHL)", "Pendientes por Asignar", "Cotizaciones Asignadas"])

    if opcion == "Nueva Cotización (Manual)":
        nueva_cotizacion_manual()
    elif opcion == "Cotizar vía API (DHL)":
        from carriers.dhl_client import cotizar_dhl, normalizar_ofertas_dhl
        st.subheader("🚚 Cotizar vía API (DHL)")

        colA, colB = st.columns(2)
        with colA:
            origen_cp = st.text_input("CP Origen", "64000")
            origen_ciudad = st.text_input("Ciudad Origen", "Monterrey")
            peso = st.number_input("Peso (kg)", min_value=0.1, value=5.0)
        with colB:
            destino_cp = st.text_input("CP Destino", "01000")
            destino_ciudad = st.text_input("Ciudad Destino", "Ciudad de México")
            dimensiones = st.text_input("Dimensiones LxAxH (cm)", "10x10x10")

        largo, ancho, alto = 10.0, 10.0, 10.0
        try:
            l, a, h = dimensiones.lower().split("x")
            largo, ancho, alto = float(l), float(a), float(h)
        except Exception:
            pass

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

                if not ofertas:
                    st.warning("DHL no devolvió precios utilizables para estos parámetros.")
                else:
                    st.success(f"{len(ofertas)} opción(es) encontradas.")
                    for of in ofertas:
                        with st.expander(f"{of['productName']} — {of['totalPrice']} {of['currency']}"):
                            st.write(f"**Código:** {of['productCode']}")
                            st.write(f"**ETA (estimado):** {of['eta'] or 'N/D'}")
                            st.json(of["raw"])

                    # 👉 Selección rápida para ofertar
                    idx = st.selectbox(
                        "Elige oferta para registrar en el sistema",
                        options=list(range(len(ofertas))),
                        format_func=lambda i: f"{ofertas[i]['productName']} - {ofertas[i]['totalPrice']} {ofertas[i]['currency']}"
                    )

                    if st.button("💾 Registrar oferta DHL"):
                        of = ofertas[idx]

                        import sqlite3, uuid
                        DB_PATH = os.path.abspath("eon.db")
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()

                        # Asegura tabla ofertas
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS ofertas (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                id_cotizacion INTEGER,
                                proveedor TEXT,
                                precio_ofertado REAL,
                                mensaje TEXT,
                                fecha TEXT
                            )
                        """)

                        # Selecciona la ultima cotización pendiente (o deja elegir)
                        df_cots = pd.read_sql_query("""
                            SELECT id, cliente, origen, destino, precio_total, fecha
                            FROM cotizaciones
                            ORDER BY fecha DESC
                        """, conn)
                        if df_cots.empty:
                            st.warning("No hay cotizaciones en la base de datos para asociar esta oferta.")
                        else:
                            # Simple: asocia a la más reciente por ahora
                            cot_id = int(df_cots.iloc[0]["id"])
                            mensaje = f"DHL {of['productName']} • ETA: {of['eta'] or 'N/D'}"

                            cursor.execute("""
                                INSERT INTO ofertas (id_cotizacion, proveedor, precio_ofertado, mensaje, fecha)
                                VALUES (?, ?, ?, ?, DATE('now'))
                            """, (cot_id, "DHL", of["totalPrice"], mensaje))
                            conn.commit()
                            conn.close()

                            st.success(f"Oferta de DHL registrada en la cotización #{cot_id}.")
            except Exception as e:
                st.error(f"Error al cotizar DHL: {e}")

    elif opcion == "Pendientes por Asignar":
        cotizaciones_pendientes()
    elif opcion == "Cotizaciones Asignadas":
        cotizaciones_asignadas()

elif menu == "Pricing":
    st.title("📈 Pricing EON")

    DB_PATH = os.path.abspath("eon.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    st.subheader("Tarifas Base por Ruta")

    # Mostrar tarifas actuales
    tarifas_df = pd.read_sql_query("SELECT * FROM tarifas", conn)
    st.dataframe(tarifas_df, use_container_width=True)

    st.markdown("### ➕ Agregar / Modificar Tarifa")
    col1, col2, col3 = st.columns(3)
    with col1:
        origen = st.text_input("Origen (Nuevo / Existente)")
    with col2:
        destino = st.text_input("Destino (Nuevo / Existente)")
    with col3:
        tarifa_base = st.number_input("Tarifa Base (MXN/km)", min_value=1.0)

    if st.button("💾 Guardar Tarifa"):
        cursor.execute("""
            INSERT INTO tarifas (origen, destino, tarifa_base)
            VALUES (?, ?, ?)
            ON CONFLICT(origen, destino) DO UPDATE SET tarifa_base=excluded.tarifa_base
        """, (origen, destino, tarifa_base))
        conn.commit()
        st.success("Tarifa guardada correctamente.")
        st.rerun()

    st.markdown("---")
    st.subheader("Márgenes de Utilidad")

    margenes_df = pd.read_sql_query("SELECT * FROM margenes", conn)
    st.dataframe(margenes_df, use_container_width=True)

    st.markdown("### ➕ Agregar / Modificar Margen")
    col1, col2, col3 = st.columns(3)
    with col1:
        criterio = st.selectbox("Criterio", ["Tipo de Unidad", "Peso"])
    with col2:
        valor = st.text_input("Valor (Ej: Camión 3.5t o 0-500kg)")
    with col3:
        margen = st.number_input("Margen (%)", min_value=0.0)

    if st.button("💾 Guardar Margen"):
        cursor.execute("""
            INSERT INTO margenes (criterio, valor, margen_porcentaje)
            VALUES (?, ?, ?)
            ON CONFLICT(criterio, valor) DO UPDATE SET margen_porcentaje=excluded.margen_porcentaje
        """, (criterio, valor, margen))
        conn.commit()
        st.success("Margen guardado correctamente.")
        st.rerun()

    conn.close()

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