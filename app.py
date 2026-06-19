import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

def clean_item_name(name):
    if not isinstance(name, str):
        return name
    # Usunięcie wielokrotnych spacji (np. podwójna spacja staje się pojedynczą)
    name = re.sub(r'\s+', ' ', name)
    # Standaryzacja ukośników - kluczowe dla Current RMS! 
    # Zamienia np. " / ", " /", "/ " na samo "/"
    name = re.sub(r'\s*/\s*', '/', name)
    # Usunięcie białych znaków na początku i na końcu nazwy
    return name.strip()

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
                    
                    # Wykrywanie początku listy sprzętowej na stronie
                    if "Quantity Item" in line or ("Quantity" in line and "Item" in line):
                        is_list_started = True
                        continue
                    
                    # Wykrywanie końca listy (podsumowanie wagi)
                    if "Total weight for:" in line:
                        is_list_started = False
                        continue
                        
                    if is_list_started and line:
                        # Szukamy wzorca: [Liczba] [Spacja] [Reszta tekstu - Nazwa sprzętu]
                        match = re.match(r'^(\d+)\s+(.+)$', line)
                        if match:
                            qty = int(match.group(1))
                            item_name = match.group(2)
                            all_items.append({"Quantity": qty, "Item": item_name})
                            
    # 1. Stworzenie tabeli ze wszystkich PDF-ów
    df = pd.DataFrame(all_items)
    if df.empty:
        return df
        
    # 2. Czyszczenie i ujednolicanie nazw sprzętu
    df['Item_Clean'] = df['Item'].apply(clean_item_name)
    
    # 3. Sumowanie (grupowanie po wyczyszczonej nazwie)
    df_grouped = df.groupby('Item_Clean', as_index=False)['Quantity'].sum()
    
    # 4. Sortowanie alfabetyczne i przygotowanie końcowej tabeli
    df_grouped = df_grouped.sort_values(by='Item_Clean').reset_index(drop=True)
    df_grouped = df_grouped.rename(columns={'Item_Clean': 'Item'})
    
    # Przestawienie kolumn (najpierw Quantity, potem Item - jak w Current RMS)
    df_grouped = df_grouped[['Quantity', 'Item']]
    
    return df_grouped

# --- INTERFEJS UŻYTKOWNIKA (STREAMLIT) ---

st.set_page_config(page_title="Analizator Current RMS", layout="wide")
st.title("📦 Zestawienie Sprzętu: Current RMS -> Excel")
st.write("Wgraj pliki PDF z listami pakunkowymi. Aplikacja ujednolici nazwy sprzętu (naprawiając błędy spacji i ukośników) oraz zsumuje pozycje z różnych kontenerów/projektów.")

uploaded_files = st.file_uploader("Wybierz pliki PDF (możesz zaznaczyć kilka na raz)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Przetwórz pliki i ujednolic listy", type="primary"):
        with st.spinner("Trwa skanowanie PDF-ów i sumowanie sprzętu..."):
            df_result = process_pdfs(uploaded_files)
            
            if not df_result.empty:
                st.success(f"Sukces! Wykryto i zsumowano unikalne pozycje sprzętowe w liczbie: {len(df_result)}.")
                
                # Wyświetlenie podglądu tabeli
                st.dataframe(df_result, use_container_width=True, height=400)
                
                # Konwersja do Excela i przycisk pobierania
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
