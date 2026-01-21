import streamlit as st
import pandas as pd
import io
import zipfile
import os
import re
from datetime import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="DORA Master Validator 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 DORA Master Validator - Controllo Multi-Sheet & Regole Custom")

# --- 1. METADATI TECNICI (DPM 4.0) ---
DORA_METADATA = {
    "b_01.01": {"desc": "Identificazione Entità", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060"]},
    "b_01.02": {"desc": "Controparti", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060", "c0070", "c0080", "c0090", "c0100", "c0110"]},
    "b_01.03": {"desc": "Filiali", "cols": ["c0010", "c0020", "c0030", "c0040"]},
    "b_02.01": {"desc": "Fornitori ICT", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050"]},
    "b_02.02": {"desc": "Gruppo Fornitori", "cols": [f"c{i:04d}" for i in range(10, 190, 10)]},
    "b_02.03": {"desc": "Fornitori Alternativi", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.01": {"desc": "Funzioni ICT", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.02": {"desc": "Mappatura Funzioni", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.03": {"desc": "Link Funzioni", "cols": ["c0010", "c0020", "c0031"]},
    "b_04.01": {"desc": "Valutazioni Rischio", "cols": ["c0010", "c0020", "c0030", "c0040"]},
    "b_05.01": {"desc": "Contratti ICT", "cols": [f"c{i:04d}" for i in range(10, 130, 10)]},
    "b_05.02": {"desc": "Subappaltatori", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060", "c0070"]},
    "b_06.01": {"desc": "Audit Sicurezza", "cols": [f"c{i:04d}" for i in range(10, 110, 10)]},
    "b_07.01": {"desc": "Strategia Uscita", "cols": [f"c{i:04d}" for i in range(10, 130, 10)]},
    "b_99.01": {"desc": "Commenti", "cols": [f"c{i:04d}" for i in range(10, 200, 10)]}
}

# --- 2. GESTIONE REGOLE (Excel rules.xlsx) ---
@st.cache_data
def load_validation_rules(uploaded_file=None):
    rules = pd.DataFrame()
    source = "Nessuna"
    if uploaded_file:
        try:
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            rules = pd.concat([df.assign(Origine=name) for name, df in xls.items()], ignore_index=True)
            source = "Manuale"
        except: pass
    elif os.path.exists("rules.xlsx"):
        try:
            xls = pd.read_excel("rules.xlsx", sheet_name=None, engine='openpyxl')
            rules = pd.concat([df.assign(Origine=name) for name, df in xls.items()], ignore_index=True)
            source = "GitHub Auto"
        except: pass
    return rules, source

# Sidebar
st.sidebar.header("🔧 Configurazione")
manual_file = st.sidebar.file_uploader("Aggiorna Regole (rules.xlsx)", type=['xlsx'])
rules_db, rules_source = load_validation_rules(manual_file)
if not rules_db.empty:
    st.sidebar.success(f"✅ Regole Attive ({rules_source}): {len(rules_db)}")

# --- 3. INTELLIGENZA DI AUDIT ---
def detect_module_code(text):
    """Cerca b_XX.XX nel testo (nome file o nome foglio)"""
    match = re.search(r"b_\d{2}\.\d{2}", text, re.IGNORECASE)
    if match: return match.group(0).lower()
    return None

def validate_dataframe(df, module_code):
    logs = []
    
    # A. VALIDAZIONE STRUTTURALE (FATAL)
    expected_cols = DORA_METADATA.get(module_code, {}).get('cols', [])
    missing_cols = [c for c in expected_cols if c not in df.columns]
    
    if missing_cols:
        logs.append({"Livello": "FATAL", "Tipo": "Struttura", "Messaggio": f"Mancano colonne: {missing_cols}", "Riga": "Header", "Colonna": "-"})
        return logs # Stop se mancano colonne

    # B. VALIDAZIONE RIGHE
    for idx, row in df.iterrows():
        riga = idx + 2
        for col in df.columns:
            val = str(row[col]).strip() if pd.notna(row[col]) else ""
            
            # 1. LEI Check
            if (col == "c0020" or "LEI" in col.upper()) and val:
                if len(val) != 20:
                    logs.append({"Livello": "ERROR", "Tipo": "LEI", "Messaggio": f"Lunghezza errata ({len(val)})", "Riga": riga, "Colonna": col})
                if not val.isalnum():
                    logs.append({"Livello": "ERROR", "Tipo": "LEI", "Messaggio": "Caratteri speciali non ammessi", "Riga": riga, "Colonna": col})

            # 2. Date Check (c0030/40 spesso date)
            if ("DATE" in col.upper() or col in ["c0030", "c0040"]) and val:
                try:
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.isna(dt):
                         logs.append({"Livello": "ERROR", "Tipo": "Data", "Messaggio": "Formato non valido", "Riga": riga, "Colonna": col})
                except: pass

    # C. REGOLE CUSTOM (rules.xlsx)
    if not rules_db.empty:
        code_key = module_code.replace("b_", "") # 05.01
        match = rules_db[rules_db.astype(str).apply(lambda x: x.str.contains(code_key, case=False)).any(axis=1)]
        if not match.empty:
            logs.append({"Livello": "INFO", "Tipo": "Compliance", "Messaggio": f"Applicate {len(match)} regole normative extra.", "Riga": "-", "Colonna": "-"})

    return logs

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["1. Audit Universale", "2. Editor Dati", "3. Export ZIP"])

if menu == "1. Audit Universale":
    st.header("🕵️‍♂️ DORA Audit - Multi-Sheet Engine")
    st.info("Carica un file Excel con più fogli (es. b_01.01, b_05.01...) oppure file CSV singoli.")
    
    uploaded_files = st.file_uploader("Trascina file qui", accept_multiple_files=True)
    
    if uploaded_files:
        st.markdown("---")
        
        # Iteriamo sui file caricati
        for file in uploaded_files:
            file_logs = []
            
            # CASO A: File EXCEL (Potrebbe avere 15 fogli!)
            if file.name.endswith('.xlsx'):
                try:
                    # Legge TUTTI i fogli insieme
                    xls_dict = pd.read_excel(file, sheet_name=None, dtype=str)
                    
                    st.subheader(f"📂 Analisi File: {file.name}")
                    
                    # Itera su ogni foglio trovato nell'Excel
                    for sheet_name, df in xls_dict.items():
                        # Cerca il codice nel nome del foglio (tab)
                        detected_mod = detect_module_code(sheet_name)
                        
                        if detected_mod and detected_mod in DORA_METADATA:
                            desc = DORA_METADATA[detected_mod]['desc']
                            
                            # Esegue audit su questo specifico foglio
                            logs = validate_dataframe(df, detected_mod)
                            
                            # Visualizza Risultati per questo foglio
                            with st.expander(f"📑 Foglio: {sheet_name} ({desc}) - {len(logs)} Segnalazioni", expanded=(len(logs)>0)):
                                if logs:
                                    log_df = pd.DataFrame(logs)
                                    st.dataframe(log_df, use_container_width=True)
                                else:
                                    st.success("✅ Validazione OK")
                        else:
                            st.warning(f"⚠️ Foglio '{sheet_name}' ignorato (Nome non standard, usa es. 'b_01.01')")
                            
                except Exception as e:
                    st.error(f"Errore lettura Excel: {e}")

            # CASO B: File CSV (Singolo foglio)
            elif file.name.endswith('.csv'):
                detected_mod = detect_module_code(file.name)
                if detected_mod:
                    df = pd.read_csv(file, sep=',', dtype=str, on_bad_lines='skip')
                    logs = validate_dataframe(df, detected_mod)
                    
                    with st.expander(f"📄 File CSV: {file.name} - {len(logs)} Segnalazioni", expanded=True):
                        if logs:
                            st.dataframe(pd.DataFrame(logs), use_container_width=True)
                        else:
                            st.success("✅ Validazione OK")
                else:
                    st.error(f"Impossibile riconoscere modulo dal nome file: {file.name}")

elif menu == "2. Editor Dati":
    st.header("📝 Inserimento Dati")
    mod = st.selectbox("Modulo", list(DORA_METADATA.keys()))
    if 'data' not in st.session_state: st.session_state['data'] = {}
    if mod not in st.session_state['data']: st.session_state['data'][mod] = pd.DataFrame(columns=DORA_METADATA[mod]['cols'])
    
    edited = st.data_editor(st.session_state['data'][mod], num_rows="dynamic", use_container_width=True)
    st.session_state['data'][mod] = edited

elif menu == "3. Export ZIP":
    st.header("📦 Genera ZIP Invio")
    if st.button("Scarica ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k in DORA_METADATA.keys():
                d = st.session_state['data'][k] if ('data' in st.session_state and k in st.session_state['data']) else pd.DataFrame(columns=DORA_METADATA[k]['cols'])
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica ZIP", buf.getvalue(), "DORA_Submission.zip", "application/zip")
