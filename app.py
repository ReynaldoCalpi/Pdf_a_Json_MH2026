import streamlit as st
import pandas as pd
import json
import io
import re
import uuid
import zipfile
from datetime import datetime
import pdfplumber

st.set_page_config(
    page_title="DTE SV Parser & JSON Suite",
    page_icon="🇸🇻",
    layout="wide"
)

# --- MÓDULO PARSER INLINE ---
def parse_pdf_to_dte_json(pdf_file) -> dict:
    """Extrae texto de PDF DTE SV y lo estructura en el schema oficial v3 JSON."""
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    # Extracciones por expresiones regulares
    tipo_dte = "03"
    if "01" in text and ("Factura" in text or "01 - Factura" in text):
        tipo_dte = "01"

    m_ctrl = re.search(r"DTE-[0-9]{2}-[A-Z0-9-]+", text)
    num_control = m_ctrl.group(0).strip() if m_ctrl else f"DTE-{tipo_dte}-M001P016-000000000000001"

    m_sello = re.search(r"Sello de Recepción:\s*([A-Z0-9-]+)", text, re.IGNORECASE)
    sello_recepcion = m_sello.group(1).strip() if m_sello else ""

    m_gen = re.search(r"Código de Generación:\s*([A-F0-9-]{36})", text, re.IGNORECASE)
    codigo_generacion = m_gen.group(1).strip() if m_gen else str(uuid.uuid4()).upper()

    m_fec = re.search(r"Fecha de Generación[:\s]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{4})", text, re.IGNORECASE)
    fec_emi = datetime.now().strftime("%Y-%m-%d")
    if m_fec:
        raw_fec = m_fec.group(1).replace("/", "-")
        if len(raw_fec.split("-")[0]) == 2:
            d, m, y = raw_fec.split("-")
            fec_emi = f"{y}-{m}-{d}"
        else:
            fec_emi = raw_fec

    m_nit_emisor = re.search(r"NIT Emisor[:\s]*([0-9-]{14,17})|NIT[:\s]*([0-9-]{14,17})", text, re.IGNORECASE)
    nit_emisor = "00000000000000"
    if m_nit_emisor:
        nit_emisor = re.sub(r'[^0-9]', '', m_nit_emisor.group(1) or m_nit_emisor.group(2) or "")

    m_nom_emisor = re.search(r"Emisor[:\s]*(.+)", text, re.IGNORECASE)
    nombre_emisor = m_nom_emisor.group(1).strip() if m_nom_emisor else "PROVEEDOR GENERICO S.A. de C.V."

    # Totales
    m_gravada = re.search(r"Ventas Gravadas[:\s]*\$?\s*([0-9,.]+)", text, re.IGNORECASE)
    m_exenta = re.search(r"Ventas Exentas[:\s]*\$?\s*([0-9,.]+)", text, re.IGNORECASE)
    m_iva = re.search(r"IVA 13%[:\s]*\$?\s*([0-9,.]+)", text, re.IGNORECASE)
    m_total = re.search(r"Total a Pagar[:\s]*\$?\s*([0-9,.]+)|Monto Total[:\s]*\$?\s*([0-9,.]+)", text, re.IGNORECASE)

    val_gravada = float((m_gravada.group(1) if m_gravada else "0").replace(",", ""))
    val_exenta = float((m_exenta.group(1) if m_exenta else "0").replace(",", ""))
    val_iva = float((m_iva.group(1) if m_iva else "0").replace(",", ""))
    val_total = float((m_total.group(1) or m_total.group(2) if m_total else "0").replace(",", ""))

    if val_total == 0 and (val_gravada > 0 or val_exenta > 0):
        val_iva = val_iva or round(val_gravada * 0.13, 2)
        val_total = round(val_gravada + val_exenta + val_iva, 2)

    dte_json = {
        "identificacion": {
            "version": 3,
            "ambiente": "01",
            "tipoDte": tipo_dte,
            "numeroControl": num_control,
            "codigoGeneracion": codigo_generacion,
            "tipoModelo": 1,
            "tipoOperacion": 1,
            "tipoContingencia": None,
            "motivoContin": None,
            "fecEmi": fec_emi,
            "horEmi": "10:00:00",
            "tipoMoneda": "USD"
        },
        "documentoRelacionado": None,
        "emisor": {
            "nit": nit_emisor,
            "nrc": "0000000",
            "nombre": nombre_emisor,
            "codActividad": "00000",
            "descActividad": "OTROS",
            "nombreComercial": nombre_emisor,
            "tipoEstablecimiento": "01",
            "direccion": {"departamento": "06", "municipio": "23", "complemento": "SAN SALVADOR"},
            "telefono": "00000000",
            "correo": "proveedor@example.com"
        },
        "receptor": {
            "nit": "06141207971019",
            "nrc": "1008013",
            "nombre": "RI CONSULTORES / CONTRIBUYENTE",
            "codActividad": "69200",
            "descActividad": "ACTIVIDADES DE CONTABILIDAD",
            "nombreComercial": "RI CONSULTORES",
            "direccion": {"departamento": "06", "municipio": "23", "complemento": "SAN SALVADOR"},
            "correo": "contacto@riconsultores.sv",
            "telefono": "22000000"
        },
        "cuerpoDocumento": [
            {
                "numItem": 1,
                "tipoItem": 1,
                "cantidad": 1.00,
                "uniMedida": 59,
                "descripcion": "CONSOLIDADO DE COMPRA / BIENES Y SERVICIOS",
                "precioUni": val_gravada + val_exenta,
                "montoDescu": 0.00,
                "ventaNoSuj": 0.00,
                "ventaExenta": val_exenta,
                "ventaGravada": val_gravada,
                "tributos": ["20"] if val_iva > 0 else None
            }
        ],
        "resumen": {
            "totalNoSuj": 0.00,
            "totalExenta": val_exenta,
            "totalGravada": val_gravada,
            "subTotalVentas": round(val_gravada + val_exenta, 2),
            "descuNoSuj": 0.00,
            "descuExenta": 0.00,
            "descuGravada": 0.00,
            "porcentajeDescuento": 0.00,
            "totalDescu": 0.00,
            "tributos": [{"codigo": "20", "descripcion": "IVA 13%", "valor": val_iva}] if val_iva > 0 else [],
            "subTotal": round(val_gravada + val_exenta, 2),
            "ivaPerci1": 0.00,
            "ivaRete1": 0.00,
            "reteRenta": 0.00,
            "montoTotalOperacion": val_total,
            "totalNoGravado": 0.00,
            "totalPagar": val_total,
            "totalLetras": "USD",
            "saldoFavor": 0.00,
            "condicionOperacion": 1,
            "pagos": [{"codigo": "01", "montoPago": val_total}]
        },
        "responseMH": {
            "version": 2,
            "ambiente": "01",
            "estado": "PROCESADO",
            "codigoGeneracion": codigo_generacion,
            "selloRecibido": sello_recepcion,
            "fhProcesamiento": f"{fec_emi} 10:00:05",
            "clasificaMsg": "10",
            "codigoMsg": "001",
            "descripcionMsg": "RECIBIDO"
        }
    }
    return dte_json

# --- UI STREAMLIT ---
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
