from fpdf import FPDF
import os

class PDFCotizacion(FPDF):
    def header(self):
        if os.path.exists("app/assets/logo_eon.jpg"):
            self.image("app/assets/logo_eon.jpg", 10, 8, 33)
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "Cotización de Envío - Eon Logistics", ln=True, align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")

def generar_pdf_cotizacion(datos, nombre_archivo):
    pdf = PDFCotizacion()
    pdf.add_page()
    pdf.set_font("Arial", "", 12)

    campos = [
        ("Fecha", datos["fecha"]),
        ("Cliente", datos["cliente"]),
        ("Origen", datos["origen"]),
        ("Destino", datos["destino"]),
        ("Distancia (km)", str(datos["distancia"])),
        ("Peso (kg)", str(datos["peso"])),
        ("Tipo de unidad", datos["tipo_unidad"]),
        ("Descripción del paquete", datos["descripcion_paquete"]),
        ("Precio total (MXN)", f"${datos['precio_total']:,.2f}")
    ]

    for campo, valor in campos:
        pdf.cell(50, 10, f"{campo}:", border=0)
        pdf.multi_cell(0, 10, valor, border=0)

    ruta_pdf = f"app/cotizaciones_pdf/{nombre_archivo}"
    os.makedirs("app/cotizaciones_pdf", exist_ok=True)
    pdf.output(ruta_pdf)
    return ruta_pdf