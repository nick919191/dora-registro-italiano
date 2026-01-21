import streamlit as st
import pandas as pd
import io
import zipfile
import os
import re
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Master Audit 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 DORA Master Validator - Report Unificato")

# --- 1. METADATI TECNICI (DPM 4.0) ---
DORA_METADATA = {
    "b_01.01": {"desc": "Identificazione Entità", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060']},
    "b_01.02": {"desc": "Controparti", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100', 'c0110']},
    "b_01.03": {"desc": "Filiali", "cols": ['c0010', 'c0020', 'c0030', 'c0040']},
    "b_02.01": {"desc": "Fornitori ICT", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050']},
    "b_02.02": {"desc": "Gruppo Fornitori", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100', 'c0110', 'c0120', 'c0130', 'c0140', 'c0150', 'c0160', 'c0170', 'c0180']},
    "b_02.03": {"desc": "Fornitori Alternativi", "cols": ['c0010', 'c0020', 'c0030']},
    "b_03.01": {"desc": "Funzioni ICT", "cols": ['c0010', 'c0020', 'c0030']},
    "b_03.02": {"desc": "Mappatura Funzioni", "cols": ['c0010', 'c0020', 'c0030']},
    "b_03.03": {"desc": "Link Funzioni", "cols": ['c0010', 'c0020', 'c0031']},
    "b_04.01": {"desc": "Valutazioni Rischio", "cols": ['c0010', 'c0020', 'c0030', 'c0040']},
    "b_05.01": {"desc": "Contratti ICT", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100', 'c0110', 'c0120']},
    "b_05.02": {"desc": "Subappaltatori", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070']},
    "b_06.01": {"desc": "Audit Sicurezza", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100']},
    "b_07.01": {"desc": "Strategia Uscita", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100', 'c0110', 'c0120']},
    "b_99.01": {"desc": "Commenti", "cols": ['c0010', 'c0020', 'c0030', 'c0040', 'c0050', 'c0060', 'c0070', 'c0080', 'c0090', 'c0100', 'c0110', 'c0120', 'c0130', 'c0140', 'c0150', 'c0160', 'c0170', 'c0180', 'c0190']}
}

# --- 2. GESTIONE REGOLE ---
@st.cache_data
def load_rules(file=None):
    rules = pd.DataFrame()
    if file: 
        try: rules = pd.concat([df.assign(Origine=n) for n,df in pd.read_excel(file, sheet_name=None).items()])
        except: pass
    elif os.path.exists("rules.xlsx"):
        try: rules = pd.concat([df.assign(Origine=n) for n,df in pd.read_excel("rules.xlsx", sheet_name=None).items()])
        except: pass
    return rules

st.sidebar.header("🔧 Configurazione")
manual_file = st.sidebar.file_uploader("Regole Custom (rules.xlsx)", type=['xlsx'])
rules_db = load_rules(manual_file)
if not rules_db.empty: st.sidebar.success(f"✅ Regole Attive: {len(rules_db)}")

# --- 3. AUDIT INTELLIGENTE (Smart Date Logic) ---
def detect_module(text):
    match = re.search(r"b_\d{2}\.\d{2}", text, re.IGNORECASE)
    return match.group(0).lower() if match else None

def validate_dataframe(df, module_code):
    logs = []
    
    # Check Header
    exp = DORA_METADATA.get(module_code, {}).get('cols', [])
    miss = [c for c in exp if c not in df.columns]
    if miss:
        return [{"Livello": "FATAL", "Tipo": "Struttura", "Messaggio": f"Mancano: {miss}", "Riga": "Header", "Colonna": "-", "Modulo": module_code}]

    # Check Righe
    for idx, row in df.iterrows():
        riga = idx + 2
        for col in df.columns:
            val = str(row[col]).strip() if pd.notna(row[col]) else ""
            
            # LEI Check (Ignora placeholder EBA)
            if (col == "c0020" or "LEI" in col.upper()) and val and "eba_" not in val.lower() and "not applicable" not in val.lower():
                if len(val) != 20 or not val.isalnum():
                    logs.append({"Livello": "ERROR", "Tipo": "LEI", "Messaggio": f"LEI invalido ({val})", "Riga": riga, "Colonna": col, "Modulo": module_code})

            # Date Check (Ignora 9999 e passate se non scadenza)
            if ("DATE" in col.upper() or col in ["c0030", "c0040", "c0060", "c0070"]) and val and "9999" not in val:
                try:
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.isna(dt):
                        logs.append({"Livello": "ERROR", "Tipo": "Data", "Messaggio": "Formato errato", "Riga": riga, "Colonna": col, "Modulo": module_code})
                    elif col == "c0040" and dt < datetime.now(): # Solo Scadenza (c0040) non deve essere passata
                        logs.append({"Livello": "WARNING", "Tipo": "Scadenza", "Messaggio": "Scaduto", "Riga": riga, "Colonna": col, "Modulo": module_code})
                except: pass

    # Regole Custom
    if not rules_db.empty:
        key = module_code.replace("b_", "")
        match = rules_db[rules_db.astype(str).apply(lambda x: x.str.contains(key, case=False)).any(axis=1)]
        if not match.empty:
            logs.append({"Livello": "INFO", "Tipo": "Compliance", "Messaggio": f"Applicate {len(match)} regole extra", "Riga": "-", "Colonna": "-", "Modulo": module_code})

    return logs

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["1. Audit Globale (Report)", "2. Editor", "3. Export ZIP"])

if menu == "1. Audit Globale (Report)":
    st.header("📊 Audit Globale & Reportistica")
    st.info("Carica il file Excel completo. Genererò un unico report con tutti gli errori.")
    
    upl = st.file_uploader("Carica Excel o CSV", accept_multiple_files=True)
    
    if upl:
        all_logs = [] # Qui raccogliamo TUTTI gli errori di TUTTI i fogli
        st.markdown("---")
        
        for file in upl:
            if file.name.endswith('.xlsx'):
                try:
                    xls = pd.read_excel(file, sheet_name=None, dtype=str)
                    st.write(f"📂 **Analisi {file.name}** ({len(xls)} fogli)")
                    
                    for sheet, df in xls.items():
                        mod = detect_module(sheet)
                        if mod and mod in DORA_METADATA:
                            res = validate_dataframe(df, mod)
                            all_logs.extend(res) # Aggiungi alla lista master
                            
                            # Visualizza anteprima veloce (Pallino colorato)
                            status = "🔴" if any(l['Livello'] in ['FATAL', 'ERROR'] for l in res) else ("🟡" if res else "🟢")
                            with st.expander(f"{status} {sheet}"):
                                if res: st.dataframe(pd.DataFrame(res))
                                else: st.success("Nessun errore")
                except Exception as e: st.error(str(e))
                
            elif file.name.endswith('.csv'):
                mod = detect_module(file.name)
                if mod:
                    df = pd.read_csv(file, sep=',', dtype=str, on_bad_lines='skip')
                    res = validate_dataframe(df, mod)
                    all_logs.extend(res)
                    status = "🔴" if any(l['Livello'] in ['FATAL', 'ERROR'] for l in res) else ("🟡" if res else "🟢")
                    with st.expander(f"{status} {file.name}"):
                        if res: st.dataframe(pd.DataFrame(res))
                        else: st.success("Nessun errore")

        # --- SEZIONE REPORT FINALE ---
        st.markdown("---")
        st.subheader("📥 Download Report Finale")
        
        if all_logs:
            report_df = pd.DataFrame(all_logs)
            
            # Statistiche
            c1, c2, c3 = st.columns(3)
            c1.metric("Totale Errori", len(report_df[report_df['Livello']=='ERROR']), delta_color="inverse")
            c2.metric("Warnings", len(report_df[report_df['Livello']=='WARNING']), delta_color="normal")
            c3.metric("Fogli Analizzati", len(report_df['Modulo'].unique()))
            
            # Bottone Download
            csv = report_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 SCARICA REPORT COMPLETO (.csv)",
                data=csv,
                file_name="DORA_Audit_Report_Full.csv",
                mime="text/csv",
                type="primary"
            )
            
            st.dataframe(report_df, use_container_width=True)
        else:
            st.balloons()
            st.success("🎉 CONGRATULAZIONI! Nessun errore rilevato in nessun foglio.")

elif menu == "2. Editor":
    st.header("📝 Editor")
    mod = st.selectbox("Modulo", list(DORA_METADATA.keys()))
    if 'data' not in st.session_state: st.session_state['data'] = {}
    if mod not in st.session_state['data']: st.session_state['data'][mod] = pd.DataFrame(columns=DORA_METADATA[mod]['cols'])
    edited = st.data_editor(st.session_state['data'][mod], num_rows="dynamic")
    st.session_state['data'][mod] = edited

elif menu == "3. Export ZIP":
    st.header("📦 Export ZIP")
    if st.button("Scarica ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k in DORA_METADATA.keys():
                d = st.session_state['data'][k] if ('data' in st.session_state and k in st.session_state['data']) else pd.DataFrame(columns=DORA_METADATA[k]['cols'])
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica", buf.getvalue(), "DORA.zip", "application/zip")
