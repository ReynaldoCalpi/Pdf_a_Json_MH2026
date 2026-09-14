import streamlit as st
import pandas as pd
import pdfplumber
import json
import io
import re

st.set_page_config(
    page_title="DTE SV Parser & Libro de Compras",
    page_icon="🇸🇻",
    layout="wide"
)

st.title("🇸🇻 Automatizador DTE PDF a Libro de Compras / MH")
st.markdown("Sube tus PDFs de DTE (Factura / CCF), genera JSON estructurado, consolida en **Libro de Compras** y exporta formato **MH**.")

# Inicialización de estado
if "processed_data" not in st.session_state:
    st.session_state.processed_data = []

def extract_dte_from_pdf(pdf_file):
    """Extrae campos clave de un PDF DTE de El Salvador usando heurísticas de texto."""
    extracted = {
        "archivo": pdf_file.name,
        "tipo_doc": "03", # Default CCF o 01 Factura
        "num_control": "",
        "sello_recepcion": "",
        "fecha_emision": "",
        "nit_proveedor": "",
        "nombre_proveedor": "",
        "compras_exentas": 0.0,
        "compras_gravadas": 0.0,
        "iva": 0.0,
        "total": 0.0
    }
    
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    # Heurísticas de expresión regular para DTE SV
    # Sello de recepción (ej: 2026A100... o similar de MH)
    m_sello = re.search(r"Sello de Recepción:\s*([A-Z0-9-]+)", text, re.IGNORECASE)
    if m_sello:
        extracted["sello_recepcion"] = m_sello.group(1).strip()
    
    # Número de control
    m_ctrl = re.search(r"DTE-[0-9]{2}-[A-Z0-9-]+", text)
    if m_ctrl:
        extracted["num_control"] = m_ctrl.group(0).strip()

    # NIT proveedor (formato salvadoreño 14 dígitos con o sin guiones)
    m_nit = re.search(r"NIT:\s*([0-9-]{14,17})", text, re.IGNORECASE)
    if m_nit:
        extracted["nit_proveedor"] = m_nit.group(1).strip()

    # Fecha emisión
    m_fecha = re.search(r"Fecha de Generación[:\s]*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})", text, re.IGNORECASE)
    if m_fecha:
        extracted["fecha_emision"] = m_fecha.group(1).strip()

    # Totales (ejemplo genérico de captura de total a pagar/iva)
    m_total = re.search(r"Total a Pagar[:\s]*\$?\s*([0-9,.]+)", text, re.IGNORECASE)
    if m_total:
        val_str = m_total.group(1).replace(",", "")
        try:
            extracted["total"] = float(val_str)
            # Estimación rápida de gravado/iva si es CCF estándar (IVA 13%)
            extracted["compras_gravadas"] = round(extracted["total"] / 1.13, 2)
            extracted["iva"] = round(extracted["total"] - extracted["compras_gravadas"], 2)
        except ValueError:
            pass

    return extracted, text

# --- SIDEBAR: Subida de Archivos ---
st.sidebar.header("📁 Carga de Documentos")
uploaded_files = st.sidebar.file_uploader(
    "Selecciona PDFs DTE", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    if st.sidebar.button("Procesar PDFs"):
        st.session_state.processed_data = []
        raw_texts = {}
        for f in uploaded_files:
            data, full_txt = extract_dte_from_pdf(f)
            st.session_state.processed_data.append(data)
            raw_texts[f.name] = full_txt
        st.sidebar.success(f"¡{len(uploaded_files)} archivos procesados!")

# --- VISTA PRINCIPAL ---
if st.session_state.processed_data:
    df_result = pd.DataFrame(st.session_state.processed_data)
    
    tab1, tab2, tab3 = st.tabs(["📊 Libro de Compras (Preview)", "{} JSON Consolidado", "📥 Exportar MH / Excel"])
    
    with tab1:
        st.subheader("Borrador de Libro de Compras")
        st.dataframe(df_result, use_container_width=True)
        
    with tab2:
        st.subheader("Estructura JSON por Documento")
        st.json(st.session_state.processed_data)

    with tab3:
        st.subheader("Generación de Salidas")
        
        # Excel Exporter
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
            df_result.to_excel(writer, sheet_name="Libro_Compras", index=False)
        output_excel.seek(0)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Descargar Libro de Compras (Excel)",
                data=output_excel,
                file_name="libro_compras_sv.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        # CSV MH format (ejemplo de estructura de consolidado)
        csv_data = df_result.to_csv(index=False, sep=";", encoding="utf-8-sig")
        with col2:
            st.download_button(
                label="📥 Descargar CSV Formato MH",
                data=csv_data,
                file_name="reporte_mh_compras.csv",
                mime="text/csv"
            )
else:
    st.info("👈 Sube uno o más PDFs en la barra lateral para comenzar el parsing.")