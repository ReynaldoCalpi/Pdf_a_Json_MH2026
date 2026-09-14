import streamlit as st
import pandas as pd
import json
import io
import zipfile

# Manejo defensivo de importación de módulos propios
try:
    from modules.parser_dte import parse_pdf_to_dte_json
except ImportError as e:
    st.error(f"Error crítico de importación en módulos: {e}. Asegúrate de que `modules/__init__.py` exista.")
    st.stop()

st.set_page_config(
    page_title="DTE SV Parser & JSON Suite",
    page_icon="🇸🇻",
    layout="wide"
)

st.title("🇸🇻 DTE PDF -> JSON Estándar v3 + Libro de Compras + CSV MH")

if "dte_collection" not in st.session_state:
    st.session_state.dte_collection = []

st.sidebar.header("📁 Carga de PDFs")
files = st.sidebar.file_uploader("Arrastra tus PDFs de DTE", type=["pdf"], accept_multiple_files=True)

if files:
    if st.sidebar.button("Procesar y Generar JSONs"):
        st.session_state.dte_collection = []
        for f in files:
            try:
                parsed_json = parse_pdf_to_dte_json(f)
                json_filename = f"{parsed_json['identificacion']['codigoGeneracion']}.json"
                st.session_state.dte_collection.append({
                    "archivo_pdf": f.name,
                    "json_filename": json_filename,
                    "data": parsed_json
                })
            except Exception as ex:
                st.sidebar.error(f"Error procesando {f.name}: {ex}")
        st.sidebar.success(f"¡Proceso finalizado!")

if st.session_state.dte_collection:
    tab1, tab2, tab3 = st.tabs(["📦 Lote de JSONs (.zip)", "📊 Libro de Compras (Excel)", "📄 CSV MH Compras"])
    
    with tab1:
        st.subheader("Archivos JSON individuales generados (formato MH)")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in st.session_state.dte_collection:
                json_bytes = json.dumps(item["data"], indent=2, ensure_ascii=False).encode('utf-8')
                zf.writestr(item["json_filename"], json_bytes)
        zip_buffer.seek(0)
        
        st.download_button(
            label="⬇️ Descargar Todos los JSONs (.zip)",
            data=zip_buffer,
            file_name="dtes_json_export.zip",
            mime="application/zip"
        )
        
        selected_idx = st.selectbox(
            "Inspeccionar JSON por documento:", 
            range(len(st.session_state.dte_collection)), 
            format_func=lambda i: st.session_state.dte_collection[i]["json_filename"]
        )
        st.json(st.session_state.dte_collection[selected_idx]["data"])

    with tab2:
        rows = []
        for item in st.session_state.dte_collection:
            d = item["data"]
            tributos = d["resumen"].get("tributos", [])
            val_iva = tributos[0]["valor"] if tributos and len(tributos) > 0 else 0.0
            rows.append({
                "Archivo PDF": item["archivo_pdf"],
                "Fec Emi": d["identificacion"]["fecEmi"],
                "Tipo DTE": d["identificacion"]["tipoDte"],
                "Num Control": d["identificacion"]["numeroControl"],
                "Sello Recibido": d["responseMH"]["selloRecibido"],
                "NIT Emisor": d["emisor"]["nit"],
                "Nombre Emisor": d["emisor"]["nombre"],
                "Exentas": d["resumen"]["totalExenta"],
                "Gravadas": d["resumen"]["totalGravada"],
                "IVA": val_iva,
                "Total Pagar": d["resumen"]["totalPagar"]
            })
        df_excel = pd.DataFrame(rows)
        st.dataframe(df_excel, use_container_width=True)
        
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as w:
            df_excel.to_excel(w, sheet_name="Libro_Compras", index=False)
        excel_buf.seek(0)
        st.download_button("📥 Descargar Libro de Compras Excel", data=excel_buf, file_name="libro_compras.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab3:
        st.write("Formato plano CSV para MH")
        csv_str = df_excel.to_csv(index=False, sep=";", encoding="utf-8-sig") if 'df_excel' in locals() and not df_excel.empty else ""
        st.download_button("📥 Descargar CSV Formato MH", data=csv_str, file_name="reporte_mh.csv", mime="text/csv")
else:
    st.info("👈 Sube tus PDFs de facturas/CCF en la barra lateral para comenzar.")
