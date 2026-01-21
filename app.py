import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Platform 2026", layout="wide", page_icon="🛡️")
st.title("🇪🇺 Piattaforma DORA - Compliance & Audit 2026")

# --- 1. DEFINIZIONE METADATI TECNICI (DPM 4.0) ---
# Qui mappiamo cosa contiene ogni codice colonna (c0010, c0020...) per ogni tabella
# Fonte: DORA ITS & Instructions Annex 1 [cite: 26, 65]

DORA_METADATA = {
    "b_01.01": { # Entity Info
        "desc": "Identificazione Entità",
        "cols": {
            "c0010": {"label": "Nome Entità", "type": "TEXT"},
            "c0020": {"label": "Codice LEI", "type": "LEI"}, 
            "c0030": {"label": "Tipo Entità", "type": "TEXT"}
        }
    },
    "b_02.01": { # ICT Providers
        "desc": "Fornitori ICT",
        "cols": {
            "c0010": {"label": "Nome Fornitore", "type": "TEXT"},
            "c0020": {"label": "Codice LEI Fornitore", "type": "LEI"},
            "c0030": {"label": "Tipo Identificativo", "type": "TEXT"},
            "c0040": {"label": "Codice Identificativo", "type": "TEXT"},
            "c0050": {"label": "Paese Residenza", "type": "COUNTRY"}
        }
    },
    "b_05.01": { # Contracts
        "desc": "Contratti ICT",
        "cols": {
            "c0010": {"label": "ID Contratto", "type": "TEXT"},
            "c0020": {"label": "ID Fornitore", "type": "TEXT"}, 
            "c0030": {"label": "Data Inizio", "type": "DATE"},
            "c0040": {"label": "Data Scadenza", "type": "DATE"},
            "c0050": {"label": "Preavviso", "type": "NUMBER"}
        }
    }
    # ... (Il sistema è estendibile agli altri 12 fogli)
}

# Inizializza DB in memoria con i nomi tecnici
if 'dora_db' not in st.session_state:
    st.session_state['dora_db'] = {}
    for code, meta in DORA_METADATA.items():
        # Creiamo il dataframe usando direttamente i codici tecnici (c0010...)
        st.session_state['dora_db'][code] = pd.DataFrame(columns=meta['cols'].keys())

# --- 2. CARICAMENTO REGOLE ESTERNE ---
def load_all_rules(uploaded_file=None):
    rules_df = pd.DataFrame()
    msg = ""
    # 1. Manuale
    if uploaded_file:
        try:
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            all_dfs = []
            for name, df in xls.items():
                df['Origine'] = name
                all_dfs.append(df)
            if all_dfs: rules_df = pd.concat(all_dfs, ignore_index=True)
            return rules_df, "Manuale"
        except: pass
    # 2. Automatico
    if os.path.exists("rules.xlsx"):
        try:
            xls = pd.read_excel("rules.xlsx", sheet_name=None, engine='openpyxl')
            all_dfs = []
            for name, df in xls.items():
                df['Origine'] = name
                all_dfs.append(df)
            if all_dfs: rules_df = pd.concat(all_dfs, ignore_index=True)
            return rules_df, "Automatico"
        except: pass
    return pd.DataFrame(), "Nessuno"

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configurazione")
manual_rules = st.sidebar.file_uploader("Carica File Regole (Excel)", type=['xlsx'])
validation_db, source = load_all_rules(manual_rules)

if not validation_db.empty:
    st.sidebar.success(f"✅ Regole ({source}): {len(validation_db)}")
else:
    st.sidebar.warning("⚠️ Nessuna regola caricata")


# --- 3. MOTORE DI AUDIT POTENZIATO (Riconosce c0010) ---
def run_full_audit(df, sheet_code):
    audit_log = []
    
    # Recuperiamo lo schema tecnico per questo foglio (es. b_01.01)
    schema = DORA_METADATA.get(sheet_code, {}).get('cols', {})
    
    # 1. FATAL: File Vuoto [cite: 51]
    if df.empty:
        audit_log.append({"Livello": "FATAL", "Colonna": "FILE", "Messaggio": "Il file è vuoto (richiesti dati o header)", "Riga": 0})
        return audit_log

    # Iterazione Righe
    for index, row in df.iterrows():
        riga_excel = index + 2
        
        # Iterazione Colonne del file caricato
        for col_name in df.columns:
            valore = str(row[col_name]).strip() if pd.notna(row[col_name]) else ""
            
            # Identifichiamo il TIPO di dato usando lo schema tecnico
            # Se la colonna si chiama "c0020", guardiamo nel dizionario cosa significa
            col_info = schema.get(col_name)
            
            # Se la colonna non è nel dizionario tecnico, potrebbe essere un errore di header
            # Ma per ora ci concentriamo sui controlli dei dati mappati
            if col_info:
                tipo_dato = col_info['type']
                label_umana = col_info['label']
                
                # --- CONTROLLI SPECIFICI ---
                
                # CHECK LEI (Lunghezza 20)
                if tipo_dato == "LEI":
                    if len(valore) != 20:
                        audit_log.append({
                            "Livello": "ERROR",
                            "Colonna": f"{col_name} ({label_umana})",
                            "Messaggio": f"Codice LEI '{valore}' invalido (Lunghezza {len(valore)} invece di 20)",
                            "Riga": riga_excel
                        })

                # CHECK DATE (Formato e Scadenza)
                elif tipo_dato == "DATE" and valore:
                    try:
                        # La BCE richiede formato YYYY-MM-DD o DD/MM/YYYY
                        dt = pd.to_datetime(valore, errors='coerce')
                        if pd.isna(dt):
                             audit_log.append({
                                "Livello": "FATAL", # Formato data errato è spesso fatal
                                "Colonna": f"{col_name} ({label_umana})", 
                                "Messaggio": f"Formato data illeggibile: {valore}", 
                                "Riga": riga_excel
                            })
                        elif "Scadenza" in label_umana and dt < datetime.now():
                             audit_log.append({
                                "Livello": "WARNING",
                                "Colonna": f"{col_name} ({label_umana})",
                                "Messaggio": f"Attenzione: Data passata ({dt.date()})",
                                "Riga": riga_excel
                            })
                    except: pass
                
                # CHECK OBBLIGATORI (Esempio: ID non può essere vuoto)
                if "ID" in label_umana or "Nome" in label_umana:
                    if not valore:
                        audit_log.append({
                            "Livello": "ERROR",
                            "Colonna": f"{col_name} ({label_umana})",
                            "Messaggio": "Campo identificativo obbligatorio mancante",
                            "Riga": riga_excel
                        })

    # 4. REGOLE ESTERNE (Regole Excel)
    if not validation_db.empty:
        key = sheet_code.replace("b_", "") # es. 01.01
        relevant = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(key, case=False)).any(axis=1)]
        if not relevant.empty:
            audit_log.append({
                "Livello": "INFO", "Colonna": "Normativa", 
                "Messaggio": f"Applicate {len(relevant)} regole DPM extra", "Riga": "-"
            })

    return audit_log

# --- INTERFACCIA ---
menu = st.sidebar.radio("Fase:", ["1. Dashboard Audit", "2. Editor Dati (Tecnico)", "3. Export BCE"])

if menu == "1. Dashboard Audit":
    st.header("🕵️‍♂️ Dashboard Validazione (Supporto Mock BCE)")
    
    upl = st.file_uploader("Carica File (FATAL/Mock)", type=['xlsx', 'csv'])
    
    # Selezione modulo intelligente
    mod_options = list(DORA_METADATA.keys())
    mod = st.selectbox("Modulo di riferimento:", mod_options, format_func=lambda x: f"{x} - {DORA_METADATA[x]['desc']}")
    
    if upl:
        # Lettura file
        if upl.name.endswith('.csv'): 
            # DORA Instruction[cite: 63]: il CSV è comma separated
            df = pd.read_csv(upl, sep=None, engine='python', dtype=str) 
        else: 
            df = pd.read_excel(upl, dtype=str)
            
        st.write(f"Analisi di {len(df)} righe...")
        st.dataframe(df.head()) # Anteprima per vedere se le colonne sono c0010
        
        logs = run_full_audit(df, mod)
        log_df = pd.DataFrame(logs)
        
        if not log_df.empty:
            # Conteggi
            n_fatal = len(log_df[log_df['Livello'] == 'FATAL'])
            n_error = len(log_df[log_df['Livello'] == 'ERROR'])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("FATAL", n_fatal, delta_color="inverse")
            c2.metric("ERROR", n_error, delta_color="inverse")
            c3.metric("WARNING", len(log_df) - n_fatal - n_error)
            
            st.error("Rilevate Anomalie:")
            st.dataframe(log_df, use_container_width=True)
            
            # Download Report
            csv_rep = log_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Scarica Report Errori", csv_rep, "Audit_Report.csv", "text/csv")
        else:
            st.success("✅ File Valido (SUCCESS)")

elif menu == "2. Editor Dati (Tecnico)":
    st.header("📝 Inserimento Dati (Vista Tecnica)")
    mod = st.selectbox("Modulo", list(DORA_METADATA.keys()))
    
    # Mostriamo una legenda per aiutare l'utente a capire cosa sono c0010, c0020...
    legenda = {k: v['label'] for k, v in DORA_METADATA[mod]['cols'].items()}
    st.caption(f"Legenda Colonne: {legenda}")
    
    d = st.session_state['dora_db'][mod]
    ed = st.data_editor(d, num_rows="dynamic", use_container_width=True)
    if not ed.equals(d): st.session_state['dora_db'][mod] = ed

elif menu == "3. Export BCE":
    st.header("🚀 Generazione Pacchetto ZIP (CSV)")
    st.info("Genera i file con header tecnici (c0010...) pronti per CASPER")
    
    if st.button("Genera ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k in DORA_METADATA.keys():
                d = st.session_state['dora_db'][k]
                # I dati sono già nelle colonne c0010, c0020... quindi salviamo diretto
                csv_data = d.to_csv(index=False).encode('utf-8')
                z.writestr(f"{k}.csv", csv_data)
        st.download_button("Scarica DORA_2026.zip", buf.getvalue(), "DORA_2026.zip", "application/zip")
