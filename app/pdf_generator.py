from fpdf import FPDF
import os
import qrcode

def generar_pdf_cotizacion(datos, nombre_archivo="cotizacion.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Encabezado
    pdf.set_font("Arial", style="B", size=14)
    pdf.cell(0, 10, "Cotización de Envío - Eon Logistics", ln=True, align="C")
    pdf.set_font("Arial", size=12)
    pdf.ln(5)

    # Datos del cliente
    pdf.cell(0, 10, f"Cliente: {datos['cliente']}", ln=True)
    pdf.cell(0, 10, f"Fecha: {datos['fecha']}", ln=True)
    pdf.cell(0, 10, f"Origen: {datos['origen']}", ln=True)
    pdf.cell(0, 10, f"Destino: {datos['destino']}", ln=True)
    pdf.cell(0, 10, f"Distancia: {datos['distancia']} km", ln=True)
    pdf.cell(0, 10, f"Peso: {datos['peso']} kg", ln=True)
    pdf.cell(0, 10, f"Tipo de unidad: {datos['tipo_unidad']}", ln=True)
    pdf.multi_cell(0, 10, f"Descripción: {datos['descripcion_paquete']}")
    pdf.cell(0, 10, f"Precio total: ${datos['precio_total']:,.2f}", ln=True)
    pdf.ln(10)

    # URL de seguimiento
    if "estatus_url" in datos:
        pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 10, "📍 Seguimiento en línea:", ln=True)
        pdf.cell(0, 10, datos["estatus_url"], ln=True, link=datos["estatus_url"])
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

        # Generar QR
        qr = qrcode.make(datos["estatus_url"])
        qr_path = f"app/cotizaciones_pdf/qr_{datos['cotizacion_id']}.png"
        qr.save(qr_path)

        # Insertar QR en PDF
        pdf.image(qr_path, x=80, y=pdf.get_y(), w=50)
        pdf.ln(60)

    # Guardar PDF
    if not os.path.exists("app/cotizaciones_pdf"):
        os.makedirs("app/cotizaciones_pdf")

    ruta_pdf = os.path.join("app/cotizaciones_pdf", nombre_archivo)
    pdf.output(ruta_pdf)

    return ruta_pdf