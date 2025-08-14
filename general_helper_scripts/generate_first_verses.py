from ScriptureReference import ScriptureReference, book_codes

def generate_first_verses_file():
    """
    Generate a text file containing the first verse of every book of the Bible
    with line numbers from the Brazilian Portuguese translation.
    """
    
    # List to store all first verses
    all_first_verses = []
    
    # Get all book codes sorted by their number
    sorted_books = sorted(book_codes.items(), key=lambda x: x[1]['number'])
    
    print("Generating first verses for all books of the Bible...")
    
    for book_code, book_info in sorted_books:
        try:
            # Get the first verse of each book (chapter 1, verse 1)
            first_verse_ref = f"{book_code} 1:1"
            
            # Create ScriptureReference with line numbers enabled
            scripture_ref = ScriptureReference(
                first_verse_ref, 
                bible_filename='source_texts/brazilian_portuguese_translation_5.txt', 
                source_type='local_ebible', 
                show_line_numbers=True
            )
            
            # Get the verse data
            if scripture_ref.verses:
                verse_data = scripture_ref.verses[0]  # Get the first (and only) verse
                line_number, verse_ref, verse_text = verse_data
                
                # Format the output
                formatted_verse = f"[{line_number}] {verse_ref}: {verse_text}"
                all_first_verses.append(formatted_verse)
                
                print(f"✓ {book_code} 1:1 - Line {line_number}")
            else:
                print(f"✗ Could not find {book_code} 1:1")
                
        except Exception as e:
            print(f"✗ Error processing {book_code}: {str(e)}")
    
    # Write all first verses to a file
    output_filename = "first_verses_all_books.txt"
    
    try:
        with open(output_filename, 'w', encoding='utf-8') as file:
            file.write("First Verse of Every Book of the Bible\n")
            file.write("Brazilian Portuguese Translation\n")
            file.write("=" * 50 + "\n\n")
            
            for verse in all_first_verses:
                file.write(verse + "\n")
        
        print(f"\n✓ Successfully generated '{output_filename}' with {len(all_first_verses)} verses")
        print(f"File saved in the current directory")
        
    except Exception as e:
        print(f"✗ Error writing to file: {str(e)}")

if __name__ == "__main__":
    generate_first_verses_file() 