import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Platform 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 Piattaforma DORA - Full Compliance Suite 2026")

# --- 1. METADATI COMPLETI (Tutti i 15 Template) ---
# Generato analizzando i file Mock FATAL della BCE
DORA_METADATA = {
    "b_01.01": {"desc": "Entity Info", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060"]},
    "b_01.02": {"desc": "Sub-consolidation", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060", "c0070", "c0080", "c0090", "c0100", "c0110"]},
    "b_01.03": {"desc": "Branches", "cols": ["c0010", "c0020", "c0030", "c0040"]},
    "b_02.01": {"desc": "ICT Providers", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050"]}, # c0020 LEI
    "b_02.02": {"desc": "Group Structure", "cols": [f"c{i:04d}" for i in range(10, 190, 10)]}, # Genera c0010...c0180
    "b_02.03": {"desc": "Alt. Providers", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.01": {"desc": "ICT Functions", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.02": {"desc": "Functions Mapping", "cols": ["c0010", "c0020", "c0030"]},
    "b_03.03": {"desc": "Function Links", "cols": ["c0010", "c0020", "c0031"]}, # Nota c0031
    "b_04.01": {"desc": "Assessments", "cols": ["c0010", "c0020", "c0030", "c0040"]},
    "b_05.01": {"desc": "Contracts", "cols": [f"c{i:04d}" for i in range(10, 130, 10)]}, # c0010...c0120
    "b_05.02": {"desc": "Sub-outsourcing", "cols": ["c0010", "c0020", "c0030", "c0040", "c0050", "c0060", "c0070"]},
    "b_06.01": {"desc": "Security Checks", "cols": [f"c{i:04d}" for i in range(10, 110, 10)]}, # c0010...c0100
    "b_07.01": {"desc": "Exit Strategy", "cols": [f"c{i:04d}" for i in range(10, 130, 10)]}, # c0010...c0120
    "b_99.01": {"desc": "Comments", "cols": [f"c{i:04d}" for i in range(10, 200, 10)]} # c0010...c0190
}

# Inizializza DB vuoto con tutte le colonne
if 'dora_db' not in st.session_state:
    st.session_state['dora_db'] = {}
    for code, meta in DORA_METADATA.items():
        st.session_state['dora_db'][code] = pd.DataFrame(columns=meta['cols'])

# --- 2. CARICAMENTO REGOLE ---
def load_rules(uploaded_file=None):
    rules_df = pd.DataFrame()
    source = "Nessuno"
    # 1. Manuale
    if uploaded_file:
        try:
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            all_dfs = [df.assign(Origine=name) for name, df in xls.items()]
            if all_dfs: rules_df = pd.concat(all_dfs, ignore_index=True); source = "Manuale"
        except: pass
    # 2. Automatico (rules.xlsx)
    elif os.path.exists("rules.xlsx"):
        try:
            xls = pd.read_excel("rules.xlsx", sheet_name=None, engine='openpyxl')
            all_dfs = [df.assign(Origine=name) for name, df in xls.items()]
            if all_dfs: rules_df = pd.concat(all_dfs, ignore_index=True); source = "GitHub Auto"
        except: pass
    return rules_df, source

st.sidebar.header("⚙️ Configurazione")
manual_rules = st.sidebar.file_uploader("Carica Regole (rules.xlsx)", type=['xlsx'])
val_db, val_source = load_rules(manual_rules)
if not val_db.empty: st.sidebar.success(f"✅ Regole attive: {len(val_db)}")

# --- 3. MOTORE DI AUDIT UNIVERSALE ---
def run_audit(df, sheet_code):
    logs = []
    
    # 1. CHECK STRUTTURALE (FATAL)
    expected_cols = DORA_METADATA.get(sheet_code, {}).get('cols', [])
    if df.empty and not expected_cols:
        return [{"Livello": "FATAL", "Messaggio": "Sheet non riconosciuto o vuoto", "Colonna": "FILE"}]
    
    # Verifica colonne mancanti
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        logs.append({"Livello": "FATAL", "Messaggio": f"Mancano colonne obbligatorie: {missing}", "Colonna": "HEADER"})

    # 2. CHECK DATI (ERROR/WARNING)
    for idx, row in df.iterrows():
        row_idx = idx + 2
        for col in df.columns:
            val = str(row[col]).strip() if pd.notna(row[col]) else ""
            
            # A. Controllo LEI (Heuristica: se la colonna è c0020 o contiene 'LEI' nel nome se mappato)
            # Nel DPM il LEI è quasi sempre c0020 o c0010. Controlliamo se il valore SEMBRA un LEI.
            # Un LEI ha 20 caratteri alfanumerici.
            if len(val) > 0:
                if (col == "c0020" or "LEI" in col.upper()) and len(val) != 20:
                     logs.append({"Livello": "ERROR", "Messaggio": f"Codice LEI invalido (Lunghezza {len(val)})", "Colonna": col, "Riga": row_idx})
                
                # B. Controllo Date (Heuristica: Valori che sembrano date YYYY-MM-DD)
                if "-" in val or "/" in val:
                    try:
                        dt = pd.to_datetime(val, errors='coerce')
                        if pd.notna(dt) and dt.year < 1900: # Data assurda
                            logs.append({"Livello": "ERROR", "Messaggio": "Data non valida", "Colonna": col, "Riga": row_idx})
                        # Warning Scadenza (Se la colonna è di tipo 'Fine' o c0040 spesso è scadenza)
                        if pd.notna(dt) and dt < datetime.now() and (col == "c0040" or "END" in col.upper()):
                            logs.append({"Livello": "WARNING", "Messaggio": "Contratto/Entità scaduta", "Colonna": col, "Riga": row_idx})
                    except: pass

    # 3. CHECK REGOLE ESTERNE (Da rules.xlsx)
    if not val_db.empty:
        # Cerca regole applicabili a questo sheet (es "06.01")
        key = sheet_code.replace("b_", "")
        match = val_db[val_db.astype(str).apply(lambda x: x.str.contains(key, case=False)).any(axis=1)]
        if not match.empty:
             logs.append({"Livello": "INFO", "Messaggio": f"Trovate {len(match)} regole normative extra.", "Colonna": "RULES", "Riga": "-"})

    return logs

# --- INTERFACCIA ---
menu = st.sidebar.radio("Navigazione:", ["1. Dashboard Audit", "2. Editor Dati", "3. Export ZIP"])

if menu == "1. Dashboard Audit":
    st.header("🕵️‍♂️ Validatore Universale (15 Templates)")
    upl = st.file_uploader("Carica File CSV/Excel", type=['csv', 'xlsx'])
    
    # Dropdown con tutti i 15 sheet
    mod_opts = list(DORA_METADATA.keys())
    sel_mod = st.selectbox("Seleziona Tipo File:", mod_opts, format_func=lambda x: f"{x} ({DORA_METADATA[x]['desc']})")

    if upl:
        if upl.name.endswith('.csv'): df = pd.read_csv(upl, sep=None, engine='python', dtype=str)
        else: df = pd.read_excel(upl, dtype=str)
        
        st.write(f"Analisi {sel_mod} ({len(df)} righe)...")
        logs = run_audit(df, sel_mod)
        
        if logs:
            log_df = pd.DataFrame(logs)
            c1, c2, c3 = st.columns(3)
            c1.metric("FATAL", len(log_df[log_df['Livello']=='FATAL']), delta_color="inverse")
            c2.metric("ERROR", len(log_df[log_df['Livello']=='ERROR']), delta_color="inverse")
            c3.metric("WARNING", len(log_df[log_df['Livello']=='WARNING']))
            
            st.dataframe(log_df, use_container_width=True)
            st.download_button("📥 Scarica Report", log_df.to_csv().encode('utf-8'), "report.csv", "text/csv")
        else:
            st.success("✅ File Valido!")

elif menu == "2. Editor Dati":
    st.header("📝 Inserimento Dati")
    sel_mod = st.selectbox("Modulo:", list(DORA_METADATA.keys()))
    df = st.session_state['dora_db'][sel_mod]
    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if not ed.equals(df): st.session_state['dora_db'][sel_mod] = ed

elif menu == "3. Export ZIP":
    st.header("🚀 Genera ZIP Invio")
    if st.button("Scarica Pacchetto"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k in DORA_METADATA.keys():
                d = st.session_state['dora_db'][k]
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica DORA_Submission.zip", buf.getvalue(), "DORA_Submission.zip", "application/zip")
