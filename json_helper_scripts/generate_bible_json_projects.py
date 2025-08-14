import json
import os
from collections import defaultdict

# Mapping from book codes to Portuguese names
book_code_to_pt_br = {
    "GEN": "Gênesis",
    "EXO": "Êxodo",
    "LEV": "Levítico",
    "NUM": "Números",
    "DEU": "Deuteronômio",
    "JOS": "Josué",
    "JDG": "Juízes",
    "RUT": "Rute",
    "1SA": "1 Samuel",
    "2SA": "2 Samuel",
    "1KI": "1 Reis",
    "2KI": "2 Reis",
    "1CH": "1 Crônicas",
    "2CH": "2 Crônicas",
    "EZR": "Esdras",
    "NEH": "Neemias",
    "EST": "Ester",
    "JOB": "Jó",
    "PSA": "Salmos",
    "PRO": "Provérbios",
    "ECC": "Eclesiastes",
    "SNG": "Cântico dos Cânticos",
    "ISA": "Isaías",
    "JER": "Jeremias",
    "LAM": "Lamentações",
    "EZK": "Ezequiel",
    "DAN": "Daniel",
    "HOS": "Oséias",
    "JOL": "Joel",
    "AMO": "Amós",
    "OBA": "Obadias",
    "JON": "Jonas",
    "MIC": "Miquéias",
    "NAM": "Naum",
    "HAB": "Habacuque",
    "ZEP": "Sofonias",
    "HAG": "Ageu",
    "ZEC": "Zacarias",
    "MAL": "Malaquias",
    "MAT": "Mateus",
    "MRK": "Marcos",
    "LUK": "Lucas",
    "JHN": "João",
    "ACT": "Atos dos Apóstolos",
    "ROM": "Romanos",
    "1CO": "1 Coríntios",
    "2CO": "2 Coríntios",
    "GAL": "Gálatas",
    "EPH": "Efésios",
    "PHP": "Filipenses",
    "COL": "Colossenses",
    "1TH": "1 Tessalonicenses",
    "2TH": "2 Tessalonicenses",
    "1TI": "1 Timóteo",
    "2TI": "2 Timóteo",
    "TIT": "Tito",
    "PHM": "Filemom",
    "HEB": "Hebreus",
    "JAS": "Tiago",
    "1PE": "1 Pedro",
    "2PE": "2 Pedro",
    "1JN": "1 João",
    "2JN": "2 João",
    "3JN": "3 João",
    "JUD": "Judas",
    "REV": "Apocalipse"
}

def convert_book_code_to_ref_format(book_code):
    """Convert book code (e.g., GEN, 1SA) to reference format (e.g., Gen, 1Sa)"""
    if book_code[0].isdigit():
        # Handle books starting with numbers (e.g., 1SA -> 1Sa)
        return book_code[0] + book_code[1].upper() + book_code[2:].lower()
    else:
        # Handle regular books (e.g., GEN -> Gen)
        return book_code[0].upper() + book_code[1:].lower()

def read_verse_references(filename):
    """Read verse references and organize by book and chapter"""
    book_chapters = defaultdict(lambda: defaultdict(list))
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) == 2:
                book_code = parts[0]
                chapter_verse = parts[1].split(':')
                if len(chapter_verse) == 2:
                    chapter = int(chapter_verse[0])
                    verse = int(chapter_verse[1])
                    book_chapters[book_code][chapter].append(verse)
    
    return book_chapters

def generate_book_json(book_code, chapters_data, pt_br_name, full_name, mission_start):
    """Generate JSON structure for a single book"""
    quests = []
    
    # Sort chapters numerically
    sorted_chapters = sorted(chapters_data.keys())
    
    for i, chapter in enumerate(sorted_chapters):
        verses = chapters_data[chapter]
        if verses:
            min_verse = min(verses)
            max_verse = max(verses)
            
            quest = {
                "name": f"{pt_br_name} Capítulo {chapter}",
                "description": "",
                "additional_tags": [f"misión:{mission_start + i}"],
                "verse_ranges": [
                    [f"{full_name} {chapter}:{min_verse}", f"{full_name} {chapter}:{max_verse}"]
                ]
            }
            quests.append(quest)
    
    json_structure = {
        "projects": [
            {
                "name": "Bíblia",
                "description": "",
                "source_language_english_name": "Brazilian Portuguese",
                "target_language_english_name": "Yanomami",
                "private": False,
                "quests": quests
            }
        ]
    }
    
    return json_structure

def main():
    # Read verse references
    print("Reading verse references...")
    book_chapters = read_verse_references("vref_eng_2.txt")
    
    # Create json_projects directory if it doesn't exist
    os.makedirs("json_projects", exist_ok=True)
    
    # Define book order (Old Testament + New Testament)
    book_order = [
        "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
        "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
        "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
        "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
        "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH",
        "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS",
        "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"
    ]
    
    mission_counter = 1
    
    # Generate JSON files for each book in order
    for book_code in book_order:
        if book_code in book_chapters and book_code in book_code_to_pt_br:
            chapters_data = book_chapters[book_code]
            pt_br_name = book_code_to_pt_br[book_code]
            full_name = convert_book_code_to_ref_format(book_code)
            
            print(f"Generating JSON for {pt_br_name} ({book_code})...")
            
            json_data = generate_book_json(book_code, chapters_data, pt_br_name, full_name, mission_counter)
            
            # Update mission counter for next book
            mission_counter += len(chapters_data)
            
            # Create filename (lowercase, replace spaces with underscores)
            filename = f"{book_code.lower()}_pt-BR.json"
            filepath = os.path.join("json_projects", filename)
            
            # Write JSON file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            print(f"  Created: {filepath}")
    
    print("\nAll JSON files have been generated!")

if __name__ == "__main__":
    main() 