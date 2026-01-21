import streamlit as st
import pandas as pd
import io
import zipfile
import os

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Platform 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 Piattaforma DORA - Compliance & Audit 2026")

# --- FUNZIONE DI CARICAMENTO FLESSIBILE ---
def load_all_rules(uploaded_file=None):
    """
    Carica le regole da due fonti possibili:
    1. Un file caricato manualmente dall'utente (Priorità Alta).
    2. Il file 'rules.xlsx' nel repository (Priorità Bassa).
    """
    rules_df = pd.DataFrame()
    source_msg = ""
    
    # 1. Caso Manuale: L'utente ha caricato un file
    if uploaded_file is not None:
        try:
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            all_dfs = []
            for sheet_name, df in xls.items():
                df['Origine_Regola'] = sheet_name 
                all_dfs.append(df)
            if all_dfs:
                rules_df = pd.concat(all_dfs, ignore_index=True)
            source_msg = "✅ Regole caricate MANUALMENTE."
            return rules_df, source_msg
        except Exception as e:
            return pd.DataFrame(), f"❌ Errore nel file manuale: {e}"

    # 2. Caso Automatico: Cerchiamo rules.xlsx nel sistema
    filename = "rules.xlsx"
    if os.path.exists(filename):
        try:
            xls = pd.read_excel(filename, sheet_name=None, engine='openpyxl')
            all_dfs = []
            for sheet_name, df in xls.items():
                df['Origine_Regola'] = sheet_name 
                all_dfs.append(df)
            if all_dfs:
                rules_df = pd.concat(all_dfs, ignore_index=True)
            source_msg = "✅ Regole caricate da GITHUB (Automatico)."
            return rules_df, source_msg
        except Exception as e:
            return pd.DataFrame(), f"❌ Errore nel file automatico: {e}"
    
    return pd.DataFrame(), "⚠️ Nessun file regole trovato."

# --- SIDEBAR: GESTIONE REGOLE ---
st.sidebar.header("⚙️ Configurazione Regole")

# Pulsante per caricamento manuale (Vince su tutto)
manual_file = st.sidebar.file_uploader("Carica File Regole (Excel)", type=['xlsx'])

# Carichiamo le regole (Manuale o Automatico)
validation_db, status_msg = load_all_rules(manual_file)

# Mostriamo lo stato nella barra laterale
if not validation_db.empty:
    st.sidebar.success(status_msg)
    st.sidebar.info(f"Controlli attivi: {len(validation_db)}")
else:
    st.sidebar.warning(status_msg)

# --- DEFINIZIONE SCHEMA DORA ---
DORA_MAP = {
    "b_01.01": {"name": "01.01 Identificazione Entità", "cols": {"Nome Entità": "c0010", "Codice LEI": "c0020"}},
    "b_02.01": {"name": "02.01 Fornitori ICT", "cols": {"Nome Fornitore": "c0010", "Codice LEI": "c0020", "Paese": "c0040", "Tipo": "c0050"}},
    "b_05.01": {"name": "05.01 Contratti ICT", "cols": {"ID Contratto": "c0010", "ID Fornitore": "c0020", "Data Inizio": "c0030", "Data Scadenza": "c0040", "Valore": "c0050"}},
}

if 'dora_db' not in st.session_state:
    st.session_state['dora_db'] = {k: pd.DataFrame(columns=v['cols'].keys()) for k, v in DORA_MAP.items()}

# --- MOTORE DI VALIDAZIONE ---
def run_audit(df, sheet_code):
    errors = []
    warnings = []
    
    if df.empty: return ["⚠️ Il foglio è vuoto."], []

    # Controlli Python base
    for col in df.columns:
        if "LEI" in col.upper():
            invalid = df[df[col].astype(str).str.len() != 20]
            if not invalid.empty:
                errors.append(f"🔴 **Errore LEI ({col}):** {len(invalid)} codici non validi.")
        if "SCADENZA" in col.upper() or "END" in col.upper():
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                scaduti = df[df[col] < pd.Timestamp.now()]
                if not scaduti.empty:
                    warnings.append(f"🟠 **Scadenze:** {len(scaduti)} contratti scaduti in '{col}'.")
            except: pass

    # Controlli dal file Excel caricato
    if not validation_db.empty:
        search_key = sheet_code.replace("b_", "")
        # Filtro flessibile: cerca il codice (es 05.01) in tutte le colonne del file regole
        relevant = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(search_key, case=False)).any(axis=1)]
        
        if not relevant.empty:
            warnings.append(f"ℹ️ **Normativa DPM:** Applicate {len(relevant)} regole ufficiali.")

    return errors, warnings

# --- INTERFACCIA PRINCIPALE ---
menu = st.sidebar.radio("Menu:", ["1. Dashboard Audit", "2. Inserimento Dati", "3. Export Finale 2026"])

if menu == "1. Dashboard Audit":
    st.header("🕵️‍♂️ Dashboard di Controllo")
    
    # Avviso sullo stato delle regole
    if validation_db.empty:
        st.error("⚠️ ATTENZIONE: Nessun file regole caricato! Carica l'Excel nella barra laterale a sinistra.")
    
    uploaded_file = st.file_uploader("Carica file dati da analizzare (CSV/Excel)", type=['xlsx', 'csv'])
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
                st.error("❌ ERRORI TECNICI")
                for e in errs: st.write(e)
            else: st.success("✅ Nessun errore tecnico")
        with c2:
            if warns:
                st.warning("⚠️ SEGNALAZIONI NORMATIVE")
                for w in warns: st.write(w)
            else: st.info("Nessuna segnalazione")

        if not validation_db.empty:
            with st.expander(f"📜 Vedi Regole Ufficiali per {sheet_type}"):
                search_key = sheet_type.replace("b_", "")
                subset = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(search_key, case=False)).any(axis=1)]
                st.dataframe(subset)

elif menu == "2. Inserimento Dati":
    st.header("📝 Editor Collaborativo")
    sheet = st.selectbox("Modulo:", list(DORA_MAP.keys()), format_func=lambda x: DORA_MAP[x]['name'])
    df = st.session_state['dora_db'][sheet]
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if not edited.equals(df): st.session_state['dora_db'][sheet] = edited

elif menu == "3. Export Finale 2026":
    st.header("🚀 Generazione Pacchetto Invio")
    if st.button("Scarica ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for code, meta in DORA_MAP.items():
                df = st.session_state['dora_db'][code].copy()
                df.rename(columns=meta['cols'], inplace=True)
                csv = df.to_csv(index=False).encode('utf-8')
                z.writestr(f"{code}.csv", csv)
        st.download_button("📥 Scarica ZIP", buf.getvalue(), "DORA_2026.zip", "application/zip")
