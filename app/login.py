import streamlit as st
import sqlite3
from cotizar_envio import cotizar_envio

def mostrar_login():
    if "usuario" not in st.session_state:
        st.subheader("🔐 Iniciar sesión")
        correo = st.text_input("Correo")
        contraseña = st.text_input("Contraseña", type="password")

        if st.button("Ingresar"):
            conn = sqlite3.connect("eon.db")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE correo = ? AND contraseña = ?", (correo, contraseña))
            usuario = cursor.fetchone()
            conn.close()

            if usuario:
                st.session_state.usuario = usuario[2]  # correo
                st.session_state.rol = usuario[4]     # rol: admin / cliente / proveedor
                st.rerun()
            else:
                st.error("❌ Correo o contraseña incorrectos")

    else:
        st.success(f"👋 Bienvenido, {st.session_state.usuario}")

        if st.session_state.rol == "cliente":
            from cliente import vista_cliente
            vista_cliente(st.session_state.usuario)

        elif st.session_state.rol == "admin":
            from admin import vista_admin
            vista_admin(st.session_state.usuario)

        elif st.session_state.rol == "proveedor":
            from proveedor import vista_proveedor
            vista_proveedor(st.session_state.usuario)

        if st.button("Cerrar sesión"):
            st.session_state.clear()
            st.rerun()