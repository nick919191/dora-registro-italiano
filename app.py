import streamlit as st
import pandas as pd
import io
import zipfile
import os
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Platform 2026", layout="wide", page_icon="🛡️")
st.title("🇪🇺 Piattaforma DORA - Compliance & Audit 2026")

# --- FUNZIONI DI CARICAMENTO ---
def load_all_rules(uploaded_file=None):
    rules_df = pd.DataFrame()
    msg = ""
    
    # 1. Manuale
    if uploaded_file:
        try:
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            all = []
            for name, df in xls.items():
                df['Origine'] = name
                all.append(df)
            if all: rules_df = pd.concat(all, ignore_index=True)
            return rules_df, "Manuale"
        except: pass
    
    # 2. Automatico (GitHub)
    if os.path.exists("rules.xlsx"):
        try:
            xls = pd.read_excel("rules.xlsx", sheet_name=None, engine='openpyxl')
            all = []
            for name, df in xls.items():
                df['Origine'] = name
                all.append(df)
            if all: rules_df = pd.concat(all, ignore_index=True)
            return rules_df, "Automatico"
        except: pass
        
    return pd.DataFrame(), "Nessuno"

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configurazione")
manual_rules = st.sidebar.file_uploader("Carica File Regole (Excel)", type=['xlsx'])
validation_db, source = load_all_rules(manual_rules)

if not validation_db.empty:
    st.sidebar.success(f"✅ Regole attive ({source}): {len(validation_db)}")
else:
    st.sidebar.warning("⚠️ Nessuna regola caricata")

# --- SCHEMA ---
DORA_MAP = {
    "b_01.01": {"name": "01.01 Entità", "cols": {"Nome": "c0010", "LEI": "c0020"}},
    "b_02.01": {"name": "02.01 Fornitori", "cols": {"Nome": "c0010", "LEI": "c0020", "Paese": "c0040"}},
    "b_05.01": {"name": "05.01 Contratti", "cols": {"ID": "c0010", "ProvID": "c0020", "Inizio": "c0030", "Fine": "c0040"}}
}

if 'dora_db' not in st.session_state:
    st.session_state['dora_db'] = {k: pd.DataFrame(columns=v['cols'].keys()) for k, v in DORA_MAP.items()}

# --- MOTORE DI AUDIT AVANZATO ---
def run_full_audit(df, sheet_code):
    """
    Restituisce una lista di dizionari con i dettagli degli errori per il report
    """
    audit_log = []
    
    # 1. FATAL ERROR (Struttura)
    if df.empty:
        audit_log.append({
            "Livello": "FATAL",
            "Colonna": "File",
            "Messaggio": "Il file è vuoto o illeggibile.",
            "Riga": 0
        })
        return audit_log # Esce subito, inutile continuare

    # Iteriamo su ogni riga per trovare Errori e Warning specifici
    for index, row in df.iterrows():
        riga_excel = index + 2 # Perchè Excel ha header e parte da 1
        
        for col in df.columns:
            valore = str(row[col]) if pd.notna(row[col]) else ""
            
            # 2. ERROR (Controlli Bloccanti)
            
            # LEI Check
            if "LEI" in col.upper():
                if len(valore) != 20:
                    audit_log.append({
                        "Livello": "ERROR",
                        "Colonna": col,
                        "Messaggio": f"Codice LEI '{valore}' non valido (lungh. {len(valore)} invece di 20)",
                        "Riga": riga_excel
                    })
            
            # Campi Obbligatori (Semplificato)
            if valore == "" or valore == "nan":
                 audit_log.append({
                        "Livello": "ERROR",
                        "Colonna": col,
                        "Messaggio": "Campo obbligatorio vuoto",
                        "Riga": riga_excel
                    })

            # 3. WARNING (Controlli di Qualità)
            
            # Scadenze
            if ("SCADENZA" in col.upper() or "FINE" in col.upper()) and valore:
                try:
                    data_obj = pd.to_datetime(row[col], errors='coerce')
                    if data_obj < pd.Timestamp.now():
                        audit_log.append({
                            "Livello": "WARNING",
                            "Colonna": col,
                            "Messaggio": f"Contratto scaduto il {data_obj.date()}",
                            "Riga": riga_excel
                        })
                except:
                    audit_log.append({"Livello": "ERROR", "Colonna": col, "Messaggio": "Formato data errato", "Riga": riga_excel})

    # 4. REGOLE ESTERNE (Dal file Excel rules.xlsx)
    if not validation_db.empty:
        # Cerca regole per questo modulo
        key = sheet_code.replace("b_", "")
        relevant = validation_db[validation_db.astype(str).apply(lambda x: x.str.contains(key, case=False)).any(axis=1)]
        
        if not relevant.empty:
            # Qui aggiungiamo un Warning generico per dire "Controlla le regole custom"
            # (In futuro si possono mappare una per una)
            audit_log.append({
                "Livello": "INFO",
                "Colonna": "Normativa",
                "Messaggio": f"Applicabili {len(relevant)} regole DPM extra (vedi sezione regole)",
                "Riga": "Tutte"
            })

    return audit_log

# --- INTERFACCIA ---
menu = st.sidebar.radio("Fase:", ["1. Dashboard Audit", "2. Editor Dati", "3. Export BCE"])

if menu == "1. Dashboard Audit":
    st.header("🕵️‍♂️ Dashboard Validazione e Report")
    
    upl = st.file_uploader("Carica Dati (Excel/CSV)", type=['xlsx', 'csv'])
    mod = st.selectbox("Modulo", list(DORA_MAP.keys()), format_func=lambda x: DORA_MAP[x]['name'])
    
    if upl:
        # Carica
        if upl.name.endswith('.csv'): df = pd.read_csv(upl, sep=None, engine='python')
        else: df = pd.read_excel(upl)
        
        st.write(f"Analisi di {len(df)} righe in corso...")
        
        # Esegue Audit
        logs = run_full_audit(df, mod)
        log_df = pd.DataFrame(logs)
        
        # Metriche
        if not log_df.empty:
            n_fatal = len(log_df[log_df['Livello'] == 'FATAL'])
            n_error = len(log_df[log_df['Livello'] == 'ERROR'])
            n_warn = len(log_df[log_df['Livello'] == 'WARNING'])
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Fatali", n_fatal, delta_color="inverse")
            col2.metric("Errori", n_error, delta_color="inverse")
            col3.metric("Warnings", n_warn, delta_color="normal")
            col4.metric("Success", len(df) - len(log_df[log_df['Riga'] != "Tutte"]))
            
            # Mostra tabella a video
            st.subheader("Dettaglio Anomalie")
            st.dataframe(log_df, use_container_width=True)
            
            # PULSANTE DOWNLOAD REPORT
            st.markdown("---")
            csv_report = log_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 SCARICA REPORT VALIDAZIONE (CSV)",
                data=csv_report,
                file_name=f"Report_Audit_{mod}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
            if n_fatal == 0 and n_error == 0:
                st.success("✅ Il file è valido per l'invio (controlla solo i Warning)!")
            else:
                st.error("⛔ Correggi gli errori Fatali/Bloccanti prima di inviare.")
                
        else:
            st.balloons()
            st.success("🎉 NESSUN ERRORE RILEVATO! VALIDAZIONE: SUCCESS.")

elif menu == "2. Editor Dati":
    st.header("📝 Inserimento Manuale")
    s = st.selectbox("Modulo", list(DORA_MAP.keys()), format_func=lambda x: DORA_MAP[x]['name'])
    d = st.session_state['dora_db'][s]
    ed = st.data_editor(d, num_rows="dynamic", use_container_width=True)
    if not ed.equals(d): st.session_state['dora_db'][s] = ed

elif menu == "3. Export BCE":
    st.header("🚀 Generazione Pacchetto ZIP")
    if st.button("Genera ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k, v in DORA_MAP.items():
                d = st.session_state['dora_db'][k].copy()
                d.rename(columns=v['cols'], inplace=True)
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica ZIP", buf.getvalue(), "DORA_2026.zip", "application/zip")
