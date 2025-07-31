import streamlit as st
import sqlite3
import pandas as pd
from utils.email_utils import enviar_email_cotizacion
from pdf_generator import generar_pdf_cotizacion

def vista_admin(usuario_admin):
    st.subheader(f"🛠️ Panel del Administrador - {usuario_admin}")
    opcion = st.selectbox("Selecciona una opción:", ["Ver cotizaciones", "Ver ofertas", "Asignar proveedor"])

    conn = sqlite3.connect("eon.db")
    cursor = conn.cursor()

    if opcion == "Ver cotizaciones":
        st.markdown("### 📦 Cotizaciones registradas")
        df = pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY fecha DESC", conn)
        st.dataframe(df, use_container_width=True)

    elif opcion == "Ver ofertas":
        st.markdown("### 💼 Ofertas enviadas por proveedores")
        df = pd.read_sql_query("""
            SELECT o.id_cotizacion, o.proveedor, o.precio_ofertado, o.mensaje, o.fecha AS fecha_oferta,
                   c.origen, c.destino, c.tipo_unidad, c.descripcion_paquete, c.cliente
            FROM ofertas o
            JOIN cotizaciones c ON o.id_cotizacion = c.id
            ORDER BY o.fecha DESC
        """, conn)
        st.dataframe(df, use_container_width=True)

    elif opcion == "Asignar proveedor":
        st.markdown("### 🧾 Asignar proveedor a una cotización")

        cursor.execute("""
            SELECT c.id, c.origen, c.destino, c.tipo_unidad, c.descripcion_paquete
            FROM cotizaciones c
            WHERE proveedor_asignado IS NULL
        """)
        cotizaciones_disponibles = cursor.fetchall()

        if cotizaciones_disponibles:
            cotizaciones_dict = {
                f"{c[0]} - {c[1]} a {c[2]} ({c[3]})": c[0] for c in cotizaciones_disponibles
            }
            seleccion = st.selectbox("Selecciona una cotización:", list(cotizaciones_dict.keys()))
            id_cotizacion = cotizaciones_dict[seleccion]

            ofertas = pd.read_sql_query(
                f"SELECT * FROM ofertas WHERE id_cotizacion = {id_cotizacion}",
                conn
            )

            if not ofertas.empty:
                st.dataframe(ofertas)
                proveedor_elegido = st.selectbox("Selecciona proveedor a asignar:", ofertas["proveedor"].unique())

                if st.button("✅ Asignar proveedor"):
                    # Asignar en BD
                    cursor.execute(
                        "UPDATE cotizaciones SET proveedor_asignado = ? WHERE id = ?",
                        (proveedor_elegido, id_cotizacion)
                    )
                    conn.commit()

                    st.success(f"Proveedor '{proveedor_elegido}' asignado correctamente.")

                    # Obtener correo del proveedor
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

                    # Obtener datos de cotización para PDF
                    cursor.execute("SELECT * FROM cotizaciones WHERE id = ?", (id_cotizacion,))
                    cotizacion = cursor.fetchone()
                    if cotizacion:
                        columnas = [col[0] for col in cursor.description]
                        datos = dict(zip(columnas, cotizacion))

                        archivo_pdf = generar_pdf_cotizacion(datos, f"cotizacion_{datos['cliente']}.pdf")

                        # Enviar al cliente
                        cursor.execute("SELECT correo FROM usuarios WHERE nombre = ?", (datos["cliente"],))
                        resultado_cliente = cursor.fetchone()

                        if resultado_cliente:
                            correo_cliente = resultado_cliente[0]
                            exito = enviar_email_cotizacion(
                                destinatario=correo_cliente,
                                archivo_pdf=archivo_pdf,
                                asunto="📦 Cotización asignada - Eon Logistics",
                                cuerpo="Tu cotización ha sido procesada y ya está siendo atendida por Eon Logistics.\n\nAdjunto encontrarás el PDF con los detalles.\n\nGracias por confiar en nosotros."
                            )
                            if exito:
                                st.success("📩 Correo con PDF enviado al cliente.")
                            else:
                                st.warning("⚠️ No se pudo enviar el PDF al cliente.")
                else:
                    st.warning("No se ha seleccionado ningún proveedor.")
            else:
                st.warning("No hay ofertas disponibles para esta cotización.")
        else:
            st.info("No hay cotizaciones pendientes por asignar.")

    cursor.close()
    conn.close()