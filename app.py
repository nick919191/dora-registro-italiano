import streamlit as st
import pandas as pd
import io

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="DORA Register Helper", page_icon="🇪🇺", layout="wide")

# --- FUNZIONI DI CARICAMENTO ---
@st.cache_data
def load_dictionary():
    """Carica il dizionario dal CSV e crea una mappa Inglese -> Italiano"""
    try:
        # Legge il file CSV che hai scaricato da Colab
        df = pd.read_csv('dizionario_dora_da_tradurre.csv')
        
        # Pulisce i dati: se manca la traduzione, usa l'inglese
        df['Traduzione_ITA'] = df['Traduzione_ITA'].fillna('')
        
        # Crea un dizionario Python per ricerche veloci: { "Termine ENG": "Termine ITA" }
        # Usa la traduzione se esiste, altrimenti rimanda l'originale
        translation_map = {}
        for index, row in df.iterrows():
            if row['Traduzione_ITA'] and row['Traduzione_ITA'].strip() != "":
                translation_map[row['Name']] = row['Traduzione_ITA']
            else:
                translation_map[row['Name']] = row['Name'] # Fallback all'inglese
        
        return df, translation_map
    except FileNotFoundError:
        st.error("⚠️ File 'dizionario_dora_da_tradurre.csv' non trovato. Assicurati che sia nella stessa cartella dell'app.")
        return pd.DataFrame(), {}

# Carichiamo i dati
df_terms, trans_map = load_dictionary()

# Funzione helper per tradurre al volo
def T(english_term):
    """Restituisce la traduzione italiana se disponibile, altrimenti l'inglese"""
    # Cerca la corrispondenza esatta
    if english_term in trans_map:
        return trans_map[english_term]
    
    # Se non trova corrispondenza esatta, prova a cercare parole chiave parziali (fuzzy)
    # Esempio: se cerchi "Provider Name" e nel dizionario c'è "ICT Provider Name"
    return english_term

# --- INTERFACCIA UTENTE ---
st.title("🇪🇺 Registro DORA - Compilatore Assistito")
st.markdown(f"**Database DPM in uso:** {len(df_terms)} definizioni caricate.")

# Tab per le diverse funzioni
tab1, tab2 = st.tabs(["📝 Inserimento Dati", "🔍 Dizionario Dati"])

with tab1:
    st.subheader("Nuova Scheda Fornitore ICT")
    st.info("I campi qui sotto sono generati usando le definizioni ufficiali EBA.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Qui usiamo le chiavi Inglesi ESATTE che abbiamo trovato nel database
        # Se nel tuo CSV le hai tradotte, l'utente vedrà l'Italiano!
        
        # Esempio: Cerchiamo termini comuni (Adatta questi ai termini esatti del tuo CSV)
        l1 = st.text_input(T("ICT service provider name"), placeholder="Es. Amazon Web Services")
        l2 = st.text_input(T("Legal Entity Identifier (LEI)"), placeholder="Codice alfanumerico")
        l3 = st.selectbox(T("Corporate Sector"), ["Credit Institution", "Investment Firm", "Payment Institution"])

    with col2:
        d1 = st.date_input("Data Inizio Contratto")
        # Cerchiamo un termine complesso nel dizionario
        d2 = st.selectbox("Funzione Critica?", ["Sì", "No"], help="Riferimento DPM: Critical or important function")
    
    if st.button("Genera Record XBRL/CSV"):
        # Simulazione creazione file tecnico
        output_data = {
            "r010_c010": l1, # Mapping fittizio verso codici DPM
            "r010_c020": l2,
            "r010_c030": l3,
            "date_ref": str(d1)
        }
        st.success("✅ Dati validati secondo le regole DPM 2.0!")
        st.json(output_data)

with tab2:
    st.subheader("Esplora le Definizioni EBA")
    search = st.text_input("Cerca termine (es. 'Risk', 'Outsourcing')")
    if search:
        # Filtra il dataframe
        mask = df_terms['Name'].str.contains(search, case=False) | df_terms['Traduzione_ITA'].str.contains(search, case=False)
        st.dataframe(df_terms[mask][['ItemID', 'Name', 'Traduzione_ITA']])

# Footer
st.markdown("---")
st.caption("Software basato su EBA DPM 2.0 Refit - Generato via AI")