# Manejador de la conexión a PostgreSQL.

import os
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            st.error("Falta la variable DATABASE_URL en el archivo .env")
            return None

        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Error crítico en la capa de datos: {e}")
        return None