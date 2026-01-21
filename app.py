import streamlit as st
import pandas as pd
import io
import zipfile
import os
import re

st.set_page_config(page_title="DORA Debugger", layout="wide")
st.title("🛠️ DORA Validator - Modalità Debug & Fix")

# --- 1. DEFINIZIONE SCHEMA (DPM 4.0) ---
DORA_METADATA = {
    "b_01.01": ["c0010", "c0020", "c0030"],
    "b_02.01": ["c0010", "c0020", "c0030", "c0040", "c0050"],
    "b_05.01": ["c0010", "c0020", "c0030", "c0040"],
    # Aggiungi qui gli altri se servono, per ora testiamo questi principali
}

# --- 2. FUNZIONE PER CAPIRE COSA VEDE L'APP ---
def analizza_file(uploaded_file):
    st.markdown("### 🔍 Analisi del File Caricato")
    
    try:
        # Tenta di leggere Excel
        xls = pd.read_excel(uploaded_file, sheet_name=None, dtype=str)
        st.success(f"✅ File Excel letto correttamente! Trovati {len(xls)} fogli.")
        
        # Mostra i nomi dei fogli trovati (così capiamo se il nome è sbagliato)
        st.write("📂 **Lista Fogli trovati nel file:**")
        st.code(list(xls.keys()))

        # Analisi Foglio per Foglio
        for sheet_name, df in xls.items():
            st.markdown(f"--- \n**Analisi Foglio:** `{sheet_name}`")
            
            # 1. CERCA IL CODICE NEL NOME
            match = re.search(r"b_\d{2}\.\d{2}", sheet_name, re.IGNORECASE)
            
            if match:
                codice_rilevato = match.group(0).lower()
                st.info(f"🔹 Riconosciuto come modulo: **{codice_rilevato}**")
                
                # 2. CONTROLLA LE COLONNE
                colonne_trovate = list(df.columns)
                st.write(f"Colonne trovate: `{colonne_trovate}`")
                
                if codice_rilevato in DORA_METADATA:
                    colonne_attese = DORA_METADATA[codice_rilevato]
                    mancanti = [c for c in colonne_attese if c not in colonne_trovate]
                    
                    if mancanti:
                        st.error(f"❌ **ERRORE STRUTTURA:** Mancano queste colonne obbligatorie: {mancanti}")
                        st.warning("⚠️ Suggerimento: Verifica che l'header (riga 1) contenga i codici tecnici (es. c0010) e non i nomi umani.")
                    else:
                        st.success("✅ Struttura Colonne OK!")
                else:
                    st.warning(f"⚠️ Il modulo {codice_rilevato} è valido ma non ho la definizione delle colonne nel codice 'DORA_METADATA'.")
            else:
                st.error(f"❌ Ignorato: Il nome del foglio '{sheet_name}' non contiene un codice DORA valido (es. 'b_01.01').")

    except Exception as e:
        st.error("🔥 **ERRORE CRITICO DI LETTURA:**")
        st.error(e)
        st.info("Se l'errore dice 'openpyxl', devi aggiungerlo in requirements.txt!")

# --- INTERFACCIA ---
uploaded_file = st.file_uploader("Carica il tuo Excel per il Debug", type=['xlsx'])

if uploaded_file:
    analizza_file(uploaded_file)
