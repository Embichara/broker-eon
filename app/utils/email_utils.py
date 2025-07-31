import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

def enviar_email_cotizacion(destinatario, archivo_pdf):
    try:
        mensaje = EmailMessage()
        mensaje["Subject"] = "📦 Tu cotización ha sido asignada - Eon Logistics"
        mensaje["From"] = EMAIL
        mensaje["To"] = destinatario
        mensaje.set_content(
            "Tu cotización ha sido procesada y ya está siendo atendida por Eon Logistics.\n\n"
            "Adjunto encontrarás el PDF con los detalles.\n\n"
            "Gracias por confiar en nosotros."
        )

        with open(archivo_pdf, "rb") as f:
            mensaje.add_attachment(f.read(), maintype="application", subtype="pdf", filename=archivo_pdf)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL, PASSWORD)
            smtp.send_message(mensaje)

        return True
    except Exception as e:
        print("❌ Error al enviar correo:", e)
        return False