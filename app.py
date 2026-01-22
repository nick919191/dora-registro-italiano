import streamlit as st
import pandas as pd
import io
import zipfile
import os
import re
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Master Validator 2026", layout="wide", page_icon="🇪🇺")
st.title("🇪🇺 DORA Master Validator 2026 (Precision, Integrity & AI Report)")

# --- 1. METADATI "PRECISION" (Tipi Espliciti) ---
DORA_METADATA = {
    "b_01.01": { "desc": "Identificazione Entità", "types": {"c0010": "LEI", "c0060": "DATE"} },
    "b_01.02": { "desc": "Controparti", "types": {"c0010": "LEI", "c0060": "LEI", "c0070": "DATE", "c0080": "DATE", "c0090": "DATE"} },
    "b_01.03": { "desc": "Filiali", "types": {"c0020": "LEI"} },
    "b_02.01": { "desc": "Fornitori ICT", "types": {"c0020": "TEXT"} }, 
    "b_02.02": { "desc": "Gruppo Fornitori", "types": {"c0030": "LEI", "c0070": "DATE", "c0080": "DATE"} },
    "b_02.03": { "desc": "Fornitori Alt.", "types": {} },
    "b_03.01": { "desc": "Funzioni ICT", "types": {} },
    "b_03.02": { "desc": "Map Funzioni", "types": {} },
    "b_03.03": { "desc": "Link Funzioni", "types": {} },
    "b_04.01": { "desc": "Rischi", "types": {"c0020": "LEI"} },
    "b_05.01": { "desc": "Contratti ICT", "types": {"c0010": "TEXT", "c0030": "DATE", "c0040": "DATE"} },
    "b_05.02": { "desc": "Subappaltatori", "types": {} },
    "b_06.01": { "desc": "Audit Sicurezza", "types": {"c0040": "LEI", "c0070": "DATE"} },
    "b_07.01": { "desc": "Strategia Uscita", "types": {"c0020": "LEI", "c0070": "DATE"} },
    "b_99.01": { "desc": "Commenti", "types": {} }
}

# --- 2. GESTIONE REGOLE (rules.xlsx) ---
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

# --- 3. MOTORE DI VALIDAZIONE AVANZATO ---

def detect_module(text):
    match = re.search(r"b_\d{2}\.\d{2}", text, re.IGNORECASE)
    return match.group(0).lower() if match else None

# A. VALIDAZIONE BASE
def validate_dataframe_basic(df, module_code):
    logs = []
    type_map = DORA_METADATA.get(module_code, {}).get('types', {})

    for idx, row in df.iterrows():
        riga = idx + 2
        for col in df.columns:
            val = str(row[col]).strip() if pd.notna(row[col]) else ""
            if not val: continue 

            col_type = type_map.get(col, "TEXT")

            if col_type == "LEI":
                if "eba_" not in val.lower() and "not applicable" not in val.lower():
                    if len(val) != 20 or not val.isalnum():
                        logs.append({"Livello": "ERROR", "Tipo": "LEI", "Messaggio": f"LEI invalido ({val})", "Riga": riga, "Colonna": col, "Modulo": module_code})

            elif col_type == "DATE":
                if "9999" in val: continue
                try:
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.isna(dt):
                        logs.append({"Livello": "ERROR", "Tipo": "Data", "Messaggio": "Formato errato", "Riga": riga, "Colonna": col, "Modulo": module_code})
                    elif col in ["c0040", "c0090"] and dt < datetime.now():
                        logs.append({"Livello": "WARNING", "Tipo": "Scadenza", "Messaggio": "Data passata", "Riga": riga, "Colonna": col, "Modulo": module_code})
                except: pass
    return logs

# B. VALIDAZIONE CROSS-COLUMN
def check_cross_column_rules(df, module_code, rules_db):
    logs = []
    if rules_db.empty: return logs
    
    relevant = rules_db[
        (rules_db['Source_Mod'] == module_code) & 
        (rules_db['Type'].isin(['CROSS_COL', 'CONDITIONAL']))
    ]

    for _, rule in relevant.iterrows():
        try:
            s_col, t_col = rule['Source_Col'], rule['Target_Col']
            op, level, msg = rule['Operator'], rule['Level'], rule['Message']
            
            if s_col not in df.columns: continue

            if op in ['<=', '<', '>=', '>'] and t_col in df.columns:
                s_dt = pd.to_datetime(df[s_col], errors='coerce')
                t_dt = pd.to_datetime(df[t_col], errors='coerce')
                mask = s_dt.notna() & t_dt.notna()
                
                if op == '<=': viol = (s_dt > t_dt) & mask
                elif op == '>=': viol = (s_dt < t_dt) & mask
                
                for idx, _ in df[viol].iterrows():
                    logs.append({"Livello": level, "Tipo": "Cross-Column", "Messaggio": msg, "Riga": idx+2, "Colonna": s_col, "Modulo": module_code})

            elif op == 'REQUIRED_IF' and t_col in df.columns:
                cond_val = rule['Condition']
                cond_mask = df[t_col].astype(str).str.strip() == str(cond_val)
                miss_mask = (df[s_col].isna()) | (df[s_col].astype(str).str.strip() == "")
                
                for idx, _ in df[cond_mask & miss_mask].iterrows():
                    logs.append({"Livello": level, "Tipo": "Condizionale", "Messaggio": f"{msg} (poiché {t_col}={cond_val})", "Riga": idx+2, "Colonna": s_col, "Modulo": module_code})

        except Exception as e: print(f"Rule Error: {e}")
    return logs

# C. VALIDAZIONE CROSS-SHEET
def check_cross_sheet_rules(all_tables, rules_db):
    logs = []
    if rules_db.empty or not all_tables: return logs
    
    cs_rules = rules_db[rules_db['Type'] == 'CROSS_SHEET']
    
    for _, rule in cs_rules.iterrows():
        try:
            s_mod, t_mod = rule['Source_Mod'], rule['Target_Mod']
            s_col, t_col = rule['Source_Col'], rule['Target_Col']
            
            if s_mod in all_tables and t_mod in all_tables:
                df_s, df_t = all_tables[s_mod], all_tables[t_mod]
                if s_col in df_s.columns and t_col in df_t.columns:
                    valid_keys = set(df_t[t_col].dropna().astype(str).str.strip())
                    s_vals = df_s[s_col].dropna().astype(str).str.strip()
                    orphans = s_vals[~s_vals.isin(valid_keys)]
                    
                    for idx, val in orphans.items():
                        logs.append({
                            "Livello": rule['Level'], "Tipo": "Integrità", 
                            "Messaggio": f"{rule['Message']} -> '{val}' mancante in {t_mod}", 
                            "Riga": idx+2, "Colonna": s_col, "Modulo": s_mod
                        })
        except: pass
    return logs

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["1. Audit Completo", "2. Editor Dati", "3. Export ZIP"])

if menu == "1. Audit Completo":
    st.header("📊 Audit Globale (Sintassi + Integrità)")
    upl = st.file_uploader("Carica Excel o CSV", accept_multiple_files=True)
    
    if 'all_tables_memory' not in st.session_state: st.session_state['all_tables_memory'] = {}
    
    if upl:
        all_logs = []
        st.session_state['all_tables_memory'] = {}
        
        # FASE 1
        st.info("🔄 Analisi Sintattica in corso...")
        for file in upl:
            dfs = {}
            if file.name.endswith('.xlsx'):
                try: dfs = pd.read_excel(file, sheet_name=None, dtype=str)
                except: st.error(f"Errore {file.name}")
            elif file.name.endswith('.csv'):
                mod = detect_module(file.name)
                if mod: dfs = {mod: pd.read_csv(file, sep=',', dtype=str, on_bad_lines='skip')}
            
            for sheet, df in dfs.items():
                mod = detect_module(sheet)
                if mod:
                    st.session_state['all_tables_memory'][mod] = df
                    res = validate_dataframe_basic(df, mod)
                    if not rules_db.empty:
                        res.extend(check_cross_column_rules(df, mod, rules_db))
                    all_logs.extend(res)

        # FASE 2
        if not rules_db.empty:
            st.info("🔄 Controllo Integrità tra Fogli...")
            res_cs = check_cross_sheet_rules(st.session_state['all_tables_memory'], rules_db)
            all_logs.extend(res_cs)
            
        # REPORT FINALE
        st.markdown("---")
        if all_logs:
            rep = pd.DataFrame(all_logs)
            c1, c2 = st.columns(2)
            c1.metric("Errori", len(rep[rep['Livello']=='ERROR']), delta_color="inverse")
            c2.metric("Warnings", len(rep[rep['Livello'].isin(['WARNING','INFO'])]), delta_color="normal")
            
            # --- AI CONTEXT SECTION (NEW) ---
            with st.expander("🤖 AI Context (Copia questo per assistenza)", expanded=False):
                st.caption("Copia questo blocco JSON e incollalo nella chat per ricevere aiuto immediato.")
                
                # Generazione Statistiche per AI
                ai_stats = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "summary": {
                        "total_logs": len(rep),
                        "fatal": int(len(rep[rep['Livello']=='FATAL'])),
                        "error": int(len(rep[rep['Livello']=='ERROR'])),
                        "warning": int(len(rep[rep['Livello']=='WARNING']))
                    },
                    # Raggruppa errori per Modulo
                    "modules_affected": rep['Modulo'].unique().tolist(),
                    "errors_by_module": rep.groupby('Modulo')['Livello'].value_counts().unstack(fill_value=0).to_dict(),
                    # Top 5 Messaggi di errore (per capire se è un problema sistematico)
                    "top_issues": rep['Messaggio'].value_counts().head(5).to_dict()
                }
                st.json(ai_stats)
            # -------------------------------

            st.subheader("Dettaglio Errori")
            st.dataframe(rep, use_container_width=True)
            st.download_button("📥 Scarica Report CSV", rep.to_csv(index=False).encode('utf-8'), "Audit_Report.csv", "text/csv", type="primary")
        else:
            st.balloons()
            st.success("🎉 File Perfetto! Nessun errore rilevato.")
            # Anche se è perfetto, diamo un contesto positivo
            with st.expander("🤖 AI Context"):
                st.json({"status": "SUCCESS", "modules": list(st.session_state['all_tables_memory'].keys())})

elif menu == "2. Editor Dati":
    st.header("📝 Editor")
    mod = st.selectbox("Modulo", list(DORA_METADATA.keys()))
    if 'data' not in st.session_state: st.session_state['data'] = {}
    if mod not in st.session_state['data']: st.session_state['data'][mod] = pd.DataFrame()
    st.session_state['data'][mod] = st.data_editor(st.session_state['data'][mod], num_rows="dynamic", use_container_width=True)

elif menu == "3. Export ZIP":
    st.header("📦 Export ZIP")
    if st.button("Genera ZIP"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            source = st.session_state.get('data', {}) or st.session_state.get('all_tables_memory', {})
            for k in DORA_METADATA.keys():
                d = source.get(k, pd.DataFrame(columns=DORA_METADATA[k].get('types', {}).keys()))
                z.writestr(f"{k}.csv", d.to_csv(index=False).encode('utf-8'))
        st.download_button("Scarica DORA.zip", buf.getvalue(), "DORA.zip", "application/zip")
