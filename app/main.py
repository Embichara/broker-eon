import streamlit as st
from login import mostrar_login

st.set_page_config(page_title="Broker Eon", page_icon="📦", layout="centered")

def main():
    st.title("📦 Sistema de Cotizaciones - Eon Logistics")
    mostrar_login()

if __name__ == "__main__":
    main()