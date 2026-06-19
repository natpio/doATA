import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import json
import google.generativeai as genai

# --- KONFIGURACJA AI GEMINI ---
# Pobieranie klucza z sekretów Streamlit Cloud
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Wymuszamy na modelu zwrot danych w formacie JSON i używamy wersji -latest
    model = genai.GenerativeModel('gemini-1.5-flash-latest', generation_config={"response_mime_type": "application/json"})
else:
    model = None

# --- BAZA TŁUMACZEŃ (SŁOWNIK LOKALNY) ---
# Twarde pozycje magazynowe, których AI ma nie ruszać.
TRANSLATIONS_DICT = {
    "1t Electric d8 + chain hoist": "Wyciągarka łańcuchowa 1t D8+",
    "Flightcase": "Skrzynia transportowa",
    "Speaker Stand": "Statyw głośnikowy",
    "LED Screen Panel": "Panel ekranu LED"
}

def clean_item_name(name):
    if not isinstance(name, str): return name
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'\s*/\s*', '/', name)
    return name.strip()

def get_ai_translations_batch(items_to_translate):
    """Wysyła paczkę nierozpoznanego sprzętu do AI z prośbą o tłumaczenie i opis"""
    if not model or not items_to_translate:
        return {}
        
    prompt = """
    Jesteś ekspertem i głównym logistykiem w firmie obsługującej duże wydarzenia multimedialne, targowe i telewizyjne. 
    Otrzymujesz listę sprzętu eventowego, AV, oświetleniowego i konstrukcyjnego. 
    Przetłumacz nazwy na profesjonalny polski żargon estradowy/magazynowy oraz dodaj zwięzły, jednozdaniowy opis przeznaczenia.
    
    Zwróć wynik WYŁĄCZNIE jako JSON w formacie listy obiektów:
    [
      {
        "oryginal": "oryginalna_nazwa_z_listy",
        "tlumaczenie": "Polska Nazwa Branżowa",
        "opis": "Krótki opis przeznaczenia sprzętu na evencie."
      }
    ]
    
    Oto lista sprzętu:
    """
    prompt += json.dumps(items_to_translate)
    
    try:
        response = model.generate_content(prompt)
        
        # Pancerne czyszczenie odpowiedzi z ewentualnych znaczników markdown dodanych przez AI
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        result_list = json.loads(raw_text.strip())
        
        # Przekształcamy listę JSON na słownik dla szybkiego dopasowywania w Pandas
        ai_dict = {}
        for item in result_list:
            ai_dict[item["oryginal"]] = {
                "tlumaczenie": item["tlumaczenie"], 
                "opis": item["opis"]
            }
        return ai_dict
    except Exception as e:
        # Ten komunikat pokaże dokładną, techniczną przyczynę błędu połączenia
        st.error(f"Szczegółowy błąd komunikacji API: {e}")
        return {}

def process_pdfs(uploaded_files):
    all_items = []
    
    for file in uploaded_files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                    
                lines = text.split('\n')
                is_list_started = False
                
                for line in lines:
                    line = line.strip()
                    if "Quantity Item" in line or ("Quantity" in line and "Item" in line):
                        is_list_started = True
                        continue
                    if "Total weight for:" in line:
                        is_list_started = False
                        continue
                        
                    if is_list_started and line:
                        match = re.match(r'^(\d+)\s+(.+)$', line)
                        if match:
                            all_items.append({"Quantity": int(match.group(1)), "Item": match.group(2)})
                            
    df = pd.DataFrame(all_items)
    if df.empty: return df
        
    df['Item_Clean'] = df['Item'].apply(clean_item_name)
    df_grouped = df.groupby('Item_Clean', as_index=False)['Quantity'].sum()
    df_grouped = df_grouped.sort_values(by='Item_Clean').reset_index(drop=True)
    
    # --- LOGIKA TŁUMACZEŃ I OPISÓW ---
    unique_items = df_grouped['Item_Clean'].tolist()
    
    # 1. Oddzielamy to co znamy, od tego co wymaga interwencji AI
    items_for_ai = [item for item in unique_items if item not in TRANSLATIONS_DICT]
    
    # 2. Wysyłamy nieznane pozycje do AI
    ai_results = {}
    if items_for_ai:
        ai_results = get_ai_translations_batch(items_for_ai)
        
    # 3. Funkcja mapująca wyniki do nowych kolumn
    def map_translation(item_name):
        if item_name in TRANSLATIONS_DICT:
            return TRANSLATIONS_DICT[item_name]
        elif item_name in ai_results:
            return ai_results[item_name]["tlumaczenie"] + " [AI]"
        return "[Brak tłumaczenia]"
        
    def map_description(item_name):
        if item_name in TRANSLATIONS_DICT:
            return "Pozycja ze słownika lokalnego"
        elif item_name in ai_results:
            return ai_results[item_name]["opis"]
        return "-"

    # Dodanie nowych kolumn
    df_grouped['Polska Nazwa'] = df_grouped['Item_Clean'].apply(map_translation)
    df_grouped['Krótki Opis'] = df_grouped['Item_Clean'].apply(map_description)
    
    # Zmiana nazw i układu kolumn
    df_grouped = df_grouped.rename(columns={'Item_Clean': 'Oryginalna Nazwa (Current RMS)'})
    df_grouped = df_grouped[['Quantity', 'Oryginalna Nazwa (Current RMS)', 'Polska Nazwa', 'Krótki Opis']]
    
    return df_grouped

# --- INTERFEJS UŻYTKOWNIKA (STREAMLIT) ---
st.set_page_config(page_title="Analizator Current RMS z AI", layout="wide")
st.title("📦 Zestawienie Sprzętu: Current RMS -> Excel (Wsparcie AI)")

if "GEMINI_API_KEY" not in st.secrets:
    st.error("⚠️ Brak konfiguracji AI. Dodaj `GEMINI_API_KEY` w ustawieniach Secrets na Streamlit Cloud.")

st.write("Wgraj pliki PDF z listami pakunkowymi. Sztuczna inteligencja przeanalizuje nieznany sprzęt, nada mu profesjonalne nazwy estradowe i wygeneruje opisy dla ekipy.")

uploaded_files = st.file_uploader("Wybierz pliki PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Przetwórz i analizuj z AI", type="primary"):
        with st.spinner("Trwa skanowanie PDF-ów i analiza sprzętu przez AI. To może potrwać kilkanaście sekund..."):
            df_result = process_pdfs(uploaded_files)
            
            if not df_result.empty:
                st.success(f"Sukces! Przeanalizowano unikalne pozycje sprzętowe: {len(df_result)}.")
                st.dataframe(df_result, use_container_width=True, height=500)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_result.to_excel(writer, index=False, sheet_name='Odprawa')
                    
                    # Formatowanie szerokości kolumn w Excelu
                    worksheet = writer.sheets['Odprawa']
                    worksheet.set_column('A:A', 10)
                    worksheet.set_column('B:B', 45)
                    worksheet.set_column('C:C', 45)
                    worksheet.set_column('D:D', 60)
                
                st.download_button(
                    label="📥 Pobierz listę Excel z opisami (.xlsx)",
                    data=buffer.getvalue(),
                    file_name="Lista_Zbiorcza_Odprawa_AI.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Nie znaleziono sprzętu. Upewnij się, że to poprawne PDF-y.")
