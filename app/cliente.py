import streamlit as st
from cotizar_envio import cotizar_envio
import sqlite3
import pandas as pd

def ver_ofertas_cliente(usuario_cliente):
    st.subheader("📬 Ofertas recibidas de proveedores")

    conn = sqlite3.connect("eon.db")

    query = """
        SELECT o.id AS id_oferta, o.id_cotizacion, o.proveedor, o.precio_ofertado, o.mensaje, o.fecha,
               c.origen, c.destino, c.descripcion_paquete, c.tipo_unidad, c.precio_total
        FROM ofertas o
        JOIN cotizaciones c ON o.id_cotizacion = c.id
        WHERE c.cliente = ?
        ORDER BY o.fecha DESC
    """

    df = pd.read_sql_query(query, conn, params=(usuario_cliente,))
    conn.close()

    if df.empty:
        st.info("Aún no has recibido ofertas de proveedores.")
    else:
        st.dataframe(df, use_container_width=True)

def ver_estado_cotizaciones(usuario_cliente):
    st.subheader("📦 Mis Cotizaciones")

    conn = sqlite3.connect("eon.db")

    query = """
        SELECT id, origen, destino, distancia_km, peso_kg, tipo_unidad, descripcion_paquete, 
               precio_total, fecha, proveedor_asignado
        FROM cotizaciones
        WHERE cliente = ?
        ORDER BY fecha DESC
    """

    df = pd.read_sql_query(query, conn, params=(usuario_cliente,))
    conn.close()

    if df.empty:
        st.info("Aún no has realizado cotizaciones.")
    else:
        for _, row in df.iterrows():
            with st.expander(f"📝 Cotización #{row['id']} - {row['origen']} → {row['destino']}"):
                st.write(f"📦 **Tipo de unidad:** {row['tipo_unidad']}")
                st.write(f"📏 **Distancia:** {row['distancia_km']} km")
                st.write(f"⚖️ **Peso:** {row['peso_kg']} kg")
                st.write(f"💬 **Descripción:** {row['descripcion_paquete']}")
                st.write(f"💲 **Precio total:** ${row['precio_total']:,.2f}")
                st.write(f"📅 **Fecha:** {row['fecha']}")

                if row["proveedor_asignado"]:
                    st.success("✅ Cotización en proceso por Eon Logistics")
                    
                    # Botón para descargar PDF
                    from pdf_generator import generar_pdf_cotizacion
                    datos_pdf = {
                        "fecha": row["fecha"],
                        "origen": row["origen"],
                        "destino": row["destino"],
                        "distancia": row["distancia_km"],
                        "peso": row["peso_kg"],
                        "descripcion_paquete": row["descripcion_paquete"],
                        "tipo_unidad": row["tipo_unidad"],
                        "precio_total": row["precio_total"],
                        "cliente": usuario_cliente
                    }
                    archivo_pdf = generar_pdf_cotizacion(datos_pdf, f"cotizacion_{usuario_cliente}_{row['id']}.pdf")

                    with open(archivo_pdf, "rb") as f:
                        st.download_button(
                            label="📄 Descargar PDF de cotización",
                            data=f,
                            file_name=archivo_pdf.split("/")[-1],
                            mime="application/pdf"
                        )
                else:
                    st.warning("⏳ Cotización aún sin asignar.")

def vista_cliente(usuario_cliente):
    st.subheader(f"👤 Bienvenido, {usuario_cliente}")
    opcion = st.selectbox(
        "Selecciona una opción:", 
        ["Cotizar envío", "Ver estado de mis cotizaciones", "Ver ofertas recibidas"]
    )

    if opcion == "Cotizar envío":
        cotizar_envio(usuario_cliente)
    elif opcion == "Ver estado de mis cotizaciones":
        ver_estado_cotizaciones(usuario_cliente)
    elif opcion == "Ver ofertas recibidas":
        ver_ofertas_cliente(usuario_cliente)