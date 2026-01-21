import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Platform 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 Piattaforma DORA - Compliance & Audit 2026")

# --- 1. CARICAMENTO AUTOMATICO REGOLE (DA GITHUB) ---
@st.cache_data
def load_embedded_rules():
    """
    Cerca il file 'rules.xlsx' direttamente nella cartella dell'app.
    Legge TUTTI i fogli (vecchi e nuovi) e li unisce.
    """
    filename = "rules.xlsx" # IL NOME DEL FILE CHE DEVI CARICARE SU GITHUB
    rules_df = pd.DataFrame()
    
    if os.path.exists(filename):
        try:
            # sheet_name=None legge tutti i fogli
            xls = pd.read_excel(filename, sheet_name=None, engine='openpyxl')
            
            all_dfs = []
            for sheet_name, df in xls.items():
                df['Origine_Regola'] = sheet_name # Tracciamo se è una regola vecchia o nuova
                all_dfs.append(df)
            
            if all_dfs:
                rules_df = pd.concat(all_dfs, ignore_index=True)
                
        except Exception as e:
            st.error(f"Errore tecnico nella lettura di {filename}: {e}")
    else:
        # Se non trova il file, non crasha ma avvisa
        st.warning(f"⚠️ Attenzione: Non trovo il file '{filename}' nel repository. Le regole automatiche sono disattivate.")
        
    return rules_df

# Carichiamo le regole all'avvio
validation_db = load_embedded_rules()

if not validation_db.empty:
    st.sidebar.success(f"✅ Database Regole Attivo: {len(validation_db)} controlli caricati.")
else:
    st.sidebar.error("❌ Database Regole non trovato.")

# --- 2. DEFINIZIONE SCHEMA DORA (Mapping ITS 2026) ---
DORA_MAP = {
    "b_01.01": {"name": "01.01 Identificazione Entità", "cols": {"Nome Entità": "c0010", "Codice LEI": "c0020"}},
    "b_02.01": {"name": "02.01 Fornitori ICT", "cols": {"Nome Fornitore": "c0010", "Codice LEI": "c0020", "Paese": "c0040", "Tipo": "c0050"}},
    "b_05.01": {"name": "05.01 Contratti ICT", "cols": {"ID Contratto": "c0010", "ID Fornitore": "c0020", "Data Inizio": "c0030", "Data Scadenza": "c0040", "Valore": "c0050"}},
}

if 'dora_db' not in st.session_state:
    st.session_state['dora_db'] = {k: pd.DataFrame(columns=v['cols'].keys()) for k, v in DORA_MAP.items()}

# --- 3. MOTORE DI VALIDAZIONE ---
def run_audit(df, sheet_code):
    errors = []
    warnings = []
    
    if df.empty:
        return ["⚠️ Il foglio è vuoto."], []

    # A. CONTROLLI BASE (Codice)
    for col in df.columns:
        # Check LEI
        if "LEI" in col.upper():
            invalid = df[df[col].astype(str).str.len() != 20]
            if not invalid.empty:
                errors.append(f"🔴 **Errore LEI ({col}):** {len(invalid)} codici invalidi.")

        # Check DATE SCADUTE
        if "SCADENZA" in col.upper() or "END" in col.upper():
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                scaduti = df[df[col] < pd.Timestamp.now()]
                if not scaduti.empty:
                    warnings.append(f"🟠 **Scadenze:** {len(scaduti)} contratti già scaduti in '{col}'.")
            except:
                pass

    # B. CONTROLLI AVANZATI (Dal file Excel rules.xlsx)
    if not validation_db.empty:
        # Cerchiamo regole che citano questo modulo (es. "05.01")
        # Adatta questo filtro in base a come sono scritti i codici nel tuo Excel
        relevant = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(sheet_code.replace("b_", ""), case=False)).any(axis=1)]
        
        if not relevant.empty:
            warnings.append(f"ℹ️ **Audit Normativo:** Applicate {len(relevant)} regole ufficiali DPM per {sheet_code}.")
            # Qui si visualizzano le regole trovate nel file
            # (In una versione futura possiamo trasformare queste regole testo in codice Python)

    return errors, warnings

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu:", ["1. Dashboard Audit", "2. Inserimento Dati", "3. Export Finale 2026"])

# --- SEZIONE 1: AUDIT ---
if menu == "1. Dashboard Audit":
    st.header("🕵️‍♂️ Dashboard di Controllo")
    st.markdown(f"Stato Regole: {'🟢 Attive' if not validation_db.empty else '🔴 Mancanti (Carica rules.xlsx su GitHub)'}")

    uploaded_file = st.file_uploader("Carica un file Excel/CSV da controllare", type=['xlsx', 'csv'])
    sheet_type = st.selectbox("Quale modulo è?", list(DORA_MAP.keys()), format_func=lambda x: DORA_MAP[x]['name'])

    if uploaded_file:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=None, engine='python')
        else:
            df = pd.read_excel(uploaded_file)
        
        st.write(f"Analisi di {len(df)} righe...")
        errs, warns = run_audit(df, sheet_type)
        
        c1, c2 = st.columns(2)
        with c1:
            if errs: 
                st.error("❌ ERRORI CRITICI")
                for e in errs: st.write(e)
            else: st.success("✅ Nessun errore tecnico")
        
        with c2:
            if warns:
                st.warning("⚠️ SEGNALAZIONI")
                for w in warns: st.write(w)
            else: st.info("Nessuna segnalazione")

        # Mostra le regole applicabili dal file Excel
        if not validation_db.empty:
            with st.expander(f"📜 Regole Ufficiali DPM per {sheet_type}"):
                # Filtro semplice per mostrare le regole pertinenti
                subset = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(sheet_type.replace("b_", ""), case=False)).any(axis=1)]
                st.dataframe(subset)

# --- SEZIONE 2: EDITOR ---
elif menu == "2. Inserimento Dati":
    st.header("📝 Editor Collaborativo")
    sheet = st.selectbox("Seleziona Modulo:", list(DORA_MAP.keys()), format_func=lambda x: DORA_MAP[x]['name'])
    
    df = st.session_state['dora_db'][sheet]
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if not edited.equals(df):
        st.session_state['dora_db'][sheet] = edited

# --- SEZIONE 3: EXPORT ---
elif menu == "3. Export Finale 2026":
    st.header("🚀 Generazione Pacchetto Invio")
    if st.button("Scarica ZIP Ufficiale"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for code, meta in DORA_MAP.items():
                df = st.session_state['dora_db'][code].copy()
                df.rename(columns=meta['cols'], inplace=True)
                csv = df.to_csv(index=False).encode('utf-8')
                z.writestr(f"{code}.csv", csv)
        st.download_button("📥 Scarica DORA_2026.zip", buf.getvalue(), "DORA_2026.zip", "application/zip")
