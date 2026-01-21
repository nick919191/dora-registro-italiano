import streamlit as st
import pandas as pd
import io
import zipfile
import os
import re
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Precision Validator", layout="wide", page_icon="🎯")
st.title("🇪🇺 DORA Precision Validator 2026")

# --- 1. METADATI "PRECISION" (Con Tipi di Dato Espliciti) ---
# TEXT = Ignora controlli (accetta tutto)
# LEI  = Controllo lunghezza 20
# DATE = Controllo formato YYYY-MM-DD
DORA_METADATA = {
    "b_01.01": {
        "desc": "Identificazione Entità",
        "types": {"c0010": "LEI", "c0060": "DATE"} # Le altre sono TEXT
    },
    "b_01.02": {
        "desc": "Controparti",
        "types": {"c0010": "LEI", "c0060": "LEI", "c0070": "DATE", "c0080": "DATE", "c0090": "DATE"}
    },
    "b_01.03": {
        "desc": "Filiali",
        "types": {"c0010": "TEXT", "c0020": "LEI"} # c0010 è ID interno
    },
    "b_02.01": {
        "desc": "Fornitori ICT",
        "types": {"c0020": "TEXT"} # Qui c0020 è un codice generico, non per forza LEI
    },
    "b_02.02": {
        "desc": "Gruppo Fornitori",
        "types": {"c0030": "LEI", "c0070": "DATE", "c0080": "DATE"}
    },
    "b_02.03": { "desc": "Fornitori Alt.", "types": {} },
    "b_03.01": { "desc": "Funzioni ICT", "types": {} },
    "b_03.02": { "desc": "Map Funzioni", "types": {} },
    "b_03.03": { "desc": "Link Funzioni", "types": {} },
    "b_04.01": { "desc": "Rischi", "types": {"c0020": "LEI"} },
    "b_05.01": {
        "desc": "Contratti ICT",
        "types": {"c0010": "TEXT", "c0030": "DATE", "c0040": "DATE"} # c0010 è Contract ID
    },
    "b_05.02": { "desc": "Subappaltatori", "types": {} },
    "b_06.01": {
        "desc": "Audit Sicurezza",
        "types": {"c0040": "LEI", "c0070": "DATE"} # c0030 qui è Funzione (Text)
    },
    "b_07.01": {
        "desc": "Strategia Uscita",
        "types": {"c0020": "LEI", "c0070": "DATE"}
    },
    "b_99.01": { "desc": "Commenti", "types": {} }
}

# --- 2. GESTIONE REGOLE CUSTOM ---
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

# --- 3. MOTORE DI AUDIT (Logic Core) ---
def detect_module(text):
    match = re.search(r"b_\d{2}\.\d{2}", text, re.IGNORECASE)
    return match.group(0).lower() if match else None

def validate_dataframe(df, module_code):
    logs = []
    
    # Recupera la mappa dei tipi per questo modulo (default TEXT se non specificato)
    type_map = DORA_METADATA.get(module_code, {}).get('types', {})

    # Check Header (Se il modulo è noto)
    if module_code in DORA_METADATA:
        # Qui potremmo controllare le colonne obbligatorie, ma per flessibilità controlliamo solo i tipi sui dati presenti
        pass

    # Check Righe
    for idx, row in df.iterrows():
        riga = idx + 2
        for col in df.columns:
            val = str(row[col]).strip() if pd.notna(row[col]) else ""
            if not val: continue # Salta celle vuote

            # Determina il tipo atteso per questa colonna
            col_type = type_map.get(col, "TEXT") # Default TEXT (Nessun controllo)

            # --- 1. CONTROLLO LEI ---
            if col_type == "LEI":
                # Ignora codici speciali EBA o N/A
                if "eba_" not in val.lower() and "not applicable" not in val.lower():
                    if len(val) != 20 or not val.isalnum():
                        logs.append({"Livello": "ERROR", "Tipo": "LEI", "Messaggio": f"Codice LEI non valido ({val})", "Riga": riga, "Colonna": col, "Modulo": module_code})

            # --- 2. CONTROLLO DATE ---
            elif col_type == "DATE":
                # Ignora 9999 (Tempo indeterminato)
                if "9999" in val: continue
                
                try:
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.isna(dt):
                        logs.append({"Livello": "ERROR", "Tipo": "Data", "Messaggio": f"Formato data errato ({val})", "Riga": riga, "Colonna": col, "Modulo": module_code})
                    else:
                        # Logica: Warning solo se è una data di scadenza (spesso c0040 o c0090) passata
                        # Euristica sicura: se la colonna è esplicitamente definita come DATE e siamo nel passato...
                        # Ma per sicurezza, warning solo su colonne 'Fine'/'End'/'Expiry' (qui semplifichiamo su c0040)
                        if col in ["c0040", "c0090"] and dt < datetime.now():
                            logs.append({"Livello": "WARNING", "Tipo": "Scadenza", "Messaggio": "Data passata (Scaduto?)", "Riga": riga, "Colonna": col, "Modulo": module_code})
                except: pass

    # Regole Custom (Excel)
    if not rules_db.empty:
        key = module_code.replace("b_", "")
        match = rules_db[rules_db.astype(str).apply(lambda x: x.str.contains(key, case=False)).any(axis=1)]
        if not match.empty:
            logs.append({"Livello": "INFO", "Tipo": "Compliance", "Messaggio": f"Regole Custom: {len(match)}", "Riga": "-", "Colonna": "-", "Modulo": module_code})

    return logs

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["1. Audit Report", "2. Editor", "3. Export ZIP"])

if menu == "1. Audit Report":
    st.header("📊 Precision Audit")
    upl = st.file_uploader("Carica File (Excel/CSV)", accept_multiple_files=True)
    
    if upl:
        all_logs = []
        st.markdown("---")
        
        for file in upl:
            # Lettura Universale
            dfs = {}
            if file.name.endswith('.xlsx'):
                try: dfs = pd.read_excel(file, sheet_name=None, dtype=str)
                except Exception as e: st.error(f"Errore {file.name}: {e}")
            elif file.name.endswith('.csv'):
                mod = detect_module(file.name)
                if mod: 
                    try: dfs = {mod: pd.read_csv(file, sep=',', dtype=str, on_bad_lines='skip')}
                    except: pass
            
            # Analisi
            for sheet, df in dfs.items():
                mod = detect_module(sheet)
                if mod:
                    res = validate_dataframe(df, mod)
                    all_logs.extend(res)
                    
                    # Feedback Visivo Immediato
                    if any(l['Livello']=='ERROR' for l in res):
                        st.error(f"🔴 {sheet}: {len(res)} Segnalazioni")
                    elif res:
                        st.warning(f"🟡 {sheet}: {len(res)} Warning/Info")
                    else:
                        st.success(f"🟢 {sheet}: OK")

        # Report Finale
        if all_logs:
            rep = pd.DataFrame(all_logs)
            st.divider()
            st.subheader("📥 Report Errori")
            
            c1, c2 = st.columns(2)
            c1.metric("Errori Bloccanti", len(rep[rep['Livello']=='ERROR']), delta_color="inverse")
            c2.metric("Avvisi / Info", len(rep[rep['Livello'].isin(['WARNING','INFO'])]), delta_color="normal")
            
            st.dataframe(rep, use_container_width=True)
            st.download_button("Scarica CSV Errori", rep.to_csv(index=False).encode('utf-8'), "DORA_Errors.csv", "text/csv", type="primary")
        else:
            if upl: st.balloons(); st.success("✅ Nessun Errore Rilevato! File Perfetto.")

elif menu == "2. Editor":
    st.header("📝 Editor")
    mod = st.selectbox("Modulo", list(DORA_METADATA.keys()))
    if 'data' not in st.session_state: st.session_state['data'] = {}
    if mod not in st.session_state['data']: st.session_state['data'][mod] = pd.DataFrame()
    st.session_state['data'][mod] = st.data_editor(st.session_state['data'][mod], num_rows="dynamic")

elif menu == "3. Export ZIP":
    st.header("📦 Export ZIP")
    if st.button("Genera ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k in DORA_METADATA.keys():
                d = st.session_state['data'].get(k, pd.DataFrame())
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica DORA.zip", buf.getvalue(), "DORA.zip", "application/zip")
