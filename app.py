import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

# --- SŁOWNIK TŁUMACZEŃ ---
# Tutaj dodawaj sprzęt ze swojego magazynu. 
# Format: "Dokładna nazwa z Current RMS": "Polskie tłumaczenie"
TRANSLATIONS_DICT = {
    "Flightcase": "Skrzynia transportowa",
    "Power Cable 2m": "Kabel zasilający 2m",
    "Speaker Stand": "Statyw głośnikowy",
    "LED Screen Panel": "Panel ekranu LED"
}

def clean_item_name(name):
    if not isinstance(name, str):
        return name
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'\s*/\s*', '/', name)
    return name.strip()

def translate_item(item_name):
    """
    Funkcja łącząca oryginalną nazwę z tłumaczeniem.
    Jeśli aplikacja nie znajdzie nazwy w słowniku, wyświetli stosowny komunikat.
    """
    polish_name = TRANSLATIONS_DICT.get(item_name)
    if polish_name:
        return f"{item_name} / {polish_name}"
    else:
        # Jeśli sprzętu nie ma w słowniku, zostawia oryginał z dopiskiem do uzupełnienia
        return f"{item_name} / [brak tłumaczenia]"

def process_pdfs(uploaded_files):
    all_items = []
    
    for file in uploaded_files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                    
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
                            qty = int(match.group(1))
                            item_name = match.group(2)
                            all_items.append({"Quantity": qty, "Item": item_name})
                            
    df = pd.DataFrame(all_items)
    if df.empty:
        return df
        
    df['Item_Clean'] = df['Item'].apply(clean_item_name)
    df_grouped = df.groupby('Item_Clean', as_index=False)['Quantity'].sum()
    df_grouped = df_grouped.sort_values(by='Item_Clean').reset_index(drop=True)
    df_grouped = df_grouped.rename(columns={'Item_Clean': 'Item'})
    
    # --- NOWA LOGIKA TŁUMACZEŃ ---
    # Tworzenie nowej kolumny na podstawie czystej nazwy 'Item'
    df_grouped['Oryginalna nazwa / Tłumaczenie polskie'] = df_grouped['Item'].apply(translate_item)
    
    # Przestawienie kolumn w pożądanej kolejności
    df_grouped = df_grouped[['Quantity', 'Item', 'Oryginalna nazwa / Tłumaczenie polskie']]
    
    return df_grouped

# --- INTERFEJS UŻYTKOWNIKA (STREAMLIT) ---
st.set_page_config(page_title="Analizator Current RMS", layout="wide")
st.title("📦 Zestawienie Sprzętu: Current RMS -> Excel")
st.write("Wgraj pliki PDF z listami pakunkowymi. Aplikacja ujednolici nazwy, zsumuje pozycje i doda polskie tłumaczenia sprzętu.")

uploaded_files = st.file_uploader("Wybierz pliki PDF (możesz zaznaczyć kilka na raz)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Przetwórz pliki i ujednolic listy", type="primary"):
        with st.spinner("Trwa skanowanie PDF-ów i sumowanie sprzętu..."):
            df_result = process_pdfs(uploaded_files)
            
            if not df_result.empty:
                st.success(f"Sukces! Wykryto i zsumowano unikalne pozycje sprzętowe w liczbie: {len(df_result)}.")
                
                st.dataframe(df_result, use_container_width=True, height=400)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_result.to_excel(writer, index=False, sheet_name='Zbiorcza')
                
                st.download_button(
                    label="📥 Pobierz wyczyszczony plik Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name="Lista_Zbiorcza_Odprawa.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Nie znaleziono żadnych pozycji sprzętowych w wgranych plikach. Upewnij się, że są to poprawne PDFy z Current RMS.")
