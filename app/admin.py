import streamlit as st
import sqlite3
import pandas as pd
from utils.email_utils import enviar_email_cotizacion
from pdf_generator import generar_pdf_cotizacion
import os
from datetime import datetime

def vista_admin(usuario_admin):
    st.subheader(f"🛠️ Panel del Administrador - {usuario_admin}")
    opcion = st.selectbox("Selecciona una opción:", ["Ver cotizaciones", "Ver ofertas", "Asignar proveedor"])

    conn = sqlite3.connect("eon.db")
    cursor = conn.cursor()

    if opcion == "Ver cotizaciones":
        st.markdown("### 📦 Cotizaciones registradas")

        # Filtros
        df = pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY fecha DESC", conn)
        df['fecha'] = pd.to_datetime(df['fecha'])

        with st.expander("🔍 Filtros"):
            fechas = st.date_input("Rango de fechas", [])
            tipo_unidad = st.multiselect("Tipo de unidad", df["tipo_unidad"].unique())
            cliente = st.text_input("Filtrar por cliente")

        # Aplicar filtros
        if fechas:
            if len(fechas) == 2:
                df = df[(df["fecha"] >= pd.to_datetime(fechas[0])) & (df["fecha"] <= pd.to_datetime(fechas[1]))]

        if tipo_unidad:
            df = df[df["tipo_unidad"].isin(tipo_unidad)]

        if cliente:
            df = df[df["cliente"].str.contains(cliente, case=False)]

        for idx, row in df.iterrows():
            with st.expander(f"Cotización {row['id']} - {row['cliente']} ({row['origen']} → {row['destino']})"):
                st.write(row)
                nombre_pdf = row.get("archivo_pdf")
                ruta_pdf = f"app/cotizaciones_pdf/{nombre_pdf}"

                if nombre_pdf and os.path.exists(ruta_pdf):
                    with open(ruta_pdf, "rb") as f:
                        st.download_button(
                            label="📄 Descargar PDF",
                            data=f,
                            file_name=nombre_pdf,
                            mime="application/pdf"
                        )
                else:
                    st.warning("⚠️ PDF no disponible para esta cotización.")

    elif opcion == "Ver ofertas":
        st.markdown("### 💼 Ofertas enviadas por proveedores")

        df = pd.read_sql_query("""
            SELECT o.id_cotizacion, o.proveedor, o.precio_ofertado, o.mensaje, o.fecha AS fecha_oferta,
                   c.origen, c.destino, c.tipo_unidad, c.descripcion_paquete, c.cliente
            FROM ofertas o
            JOIN cotizaciones c ON o.id_cotizacion = c.id
            ORDER BY o.fecha DESC
        """, conn)
        df["fecha_oferta"] = pd.to_datetime(df["fecha_oferta"])

        with st.expander("🔍 Filtros"):
            fechas = st.date_input("Rango de fechas", [])
            tipo_unidad = st.multiselect("Tipo de unidad", df["tipo_unidad"].unique())
            proveedor = st.text_input("Filtrar por proveedor")

        if fechas:
            if len(fechas) == 2:
                df = df[(df["fecha_oferta"] >= pd.to_datetime(fechas[0])) & (df["fecha_oferta"] <= pd.to_datetime(fechas[1]))]

        if tipo_unidad:
            df = df[df["tipo_unidad"].isin(tipo_unidad)]

        if proveedor:
            df = df[df["proveedor"].str.contains(proveedor, case=False)]

        st.dataframe(df, use_container_width=True)

    elif opcion == "Asignar proveedor":
        st.markdown("### 🧾 Asignar proveedor a una cotización")

        cursor.execute("""
            SELECT c.id, c.origen, c.destino, c.tipo_unidad, c.descripcion_paquete, c.cliente
            FROM cotizaciones c
            WHERE proveedor_asignado IS NULL
        """)
        cotizaciones_disponibles = cursor.fetchall()

        if cotizaciones_disponibles:
            df_cotizaciones = pd.DataFrame(cotizaciones_disponibles, columns=["id", "origen", "destino", "tipo_unidad", "descripcion_paquete", "cliente"])

            with st.expander("🔍 Filtros"):
                cliente_filtro = st.text_input("Filtrar por cliente")
                origen_filtro = st.text_input("Filtrar por origen")
                destino_filtro = st.text_input("Filtrar por destino")
                tipo_unidad_filtro = st.multiselect("Tipo de unidad", df_cotizaciones["tipo_unidad"].unique())

                if cliente_filtro:
                    df_cotizaciones = df_cotizaciones[df_cotizaciones["cliente"].str.contains(cliente_filtro, case=False)]
                if origen_filtro:
                    df_cotizaciones = df_cotizaciones[df_cotizaciones["origen"].str.contains(origen_filtro, case=False)]
                if destino_filtro:
                    df_cotizaciones = df_cotizaciones[df_cotizaciones["destino"].str.contains(destino_filtro, case=False)]
                if tipo_unidad_filtro:
                    df_cotizaciones = df_cotizaciones[df_cotizaciones["tipo_unidad"].isin(tipo_unidad_filtro)]

            if df_cotizaciones.empty:
                st.info("🔎 No hay cotizaciones pendientes con los filtros seleccionados.")
            else:
                seleccion = st.selectbox(
                    "Selecciona una cotización pendiente:",
                    [f"{row['id']} - {row['origen']} → {row['destino']} ({row['tipo_unidad']})" for _, row in df_cotizaciones.iterrows()]
                )
                id_cotizacion = int(seleccion.split(" - ")[0])

                ofertas = pd.read_sql_query(
                    f"SELECT * FROM ofertas WHERE id_cotizacion = {id_cotizacion}",
                    conn
                )

                if not ofertas.empty:
                    st.dataframe(ofertas)
                    proveedor_elegido = st.selectbox("Selecciona proveedor a asignar:", ofertas["proveedor"].unique())

                    if st.button("✅ Asignar proveedor"):
                        # Actualiza base de datos
                        cursor.execute("UPDATE cotizaciones SET proveedor_asignado = ? WHERE id = ?", (proveedor_elegido, id_cotizacion))
                        conn.commit()

                        st.success(f"Proveedor '{proveedor_elegido}' asignado correctamente.")

                        # Email a proveedor
                        cursor.execute("SELECT correo FROM usuarios WHERE nombre = ?", (proveedor_elegido,))
                        resultado = cursor.fetchone()
                        if resultado:
                            correo_proveedor = resultado[0]
                            enviar_email_cotizacion(
                                destinatario=correo_proveedor,
                                asunto="🚚 Nueva asignación de envío",
                                cuerpo=f"Hola {proveedor_elegido},\n\nSe te ha asignado un nuevo envío (Cotización ID: {id_cotizacion}).\n\nRevisa el sistema.\n\nGracias,\nEon Logistics"
                            )
                            st.info(f"📧 Correo enviado a {correo_proveedor}.")
                        else:
                            st.warning("⚠️ No se encontró el correo del proveedor.")

                        # Generar PDF y enviar al cliente
                        cursor.execute("SELECT * FROM cotizaciones WHERE id = ?", (id_cotizacion,))
                        cotizacion = cursor.fetchone()
                        columnas = [col[0] for col in cursor.description]
                        datos = dict(zip(columnas, cotizacion))

                        import uuid
                        datos["cotizacion_id"] = datos.get("cotizacion_id") or str(uuid.uuid4())[:8]
                        datos["fecha"] = datos.get("fecha") or datetime.now().strftime("%Y-%m-%d")
                        datos["estatus_url"] = f"https://eonlogisticgroup.com/estatus/{datos['cotizacion_id']}"

                        try:
                            archivo_pdf = generar_pdf_cotizacion(datos, f"cotizacion_{datos['cliente']}.pdf")
                            cursor.execute("UPDATE cotizaciones SET archivo_pdf = ?, cotizacion_id = ? WHERE id = ?", (os.path.basename(archivo_pdf), datos["cotizacion_id"], id_cotizacion))
                            conn.commit()
                        except Exception as e:
                            st.error(f"❌ Error al generar el PDF: {e}")
                            return

                        # Email al cliente
                        cursor.execute("SELECT correo FROM usuarios WHERE nombre = ?", (datos["cliente"],))
                        resultado_cliente = cursor.fetchone()
                        if resultado_cliente:
                            correo_cliente = resultado_cliente[0]
                            enviado = enviar_email_cotizacion(
                                destinatario=correo_cliente,
                                archivo_pdf=archivo_pdf,
                                asunto="📦 Cotización asignada - Eon Logistics",
                                cuerpo="Tu cotización ha sido procesada y ya está siendo atendida por Eon Logistics.\n\nAdjunto encontrarás el PDF con los detalles.\n\nGracias por confiar en nosotros."
                            )
                            if enviado:
                                st.success("📩 Correo con PDF enviado al cliente.")
                            else:
                                st.warning("⚠️ No se pudo enviar el PDF al cliente.")
                else:
                    st.warning("⚠️ No hay ofertas disponibles para esta cotización.")
        else:
            st.info("No hay cotizaciones pendientes por asignar.")

    cursor.close()
    conn.close()