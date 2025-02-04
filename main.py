import os
from datetime import datetime
import uuid
import csv
from dotenv import load_dotenv
from ScriptureReference import ScriptureReference
from elevenlabs_narrate import process_verses

def generate_filename(verse_ref, config):
    """Generate filename based on configuration"""
    parts = []
    
    if config.get('prefix'):
        parts.append(str(config['prefix']))
    
    if config.get('include_verse_name', True):
        parts.append(str(verse_ref))
        
    if config.get('include_uuid', False):
        parts.append(str(uuid.uuid4()))
        
    if config.get('suffix'):
        parts.append(str(config['suffix']))
    
    # Join parts with underscore and add extension
    filename = '_'.join(filter(None, parts))  # filter(None) removes empty strings
    return filename + '.mp3'

def generate_bible_audio(start_ref, end_ref, config):
    """
    Generate audio files for Bible verses with the specified configuration.
    
    Args:
        start_ref (str): Starting scripture reference (e.g., "John 3:16")
        end_ref (str): Ending scripture reference (e.g., "John 3:18")
        config (dict): Configuration dictionary containing:
            - translation: e-bible translation code
            - output_folder: base folder for output
            - filename_config: dict with prefix, suffix, include_uuid, include_verse_name
            - voice: ElevenLabs voice to use
    """
    # Load environment variables
    load_dotenv()
    
    # Get verses from ScriptureReference
    scripture = ScriptureReference(
        start_ref, 
        end_ref, 
        bible_filename=config.get('translation', os.getenv('DEFAULT_TRANSLATION'))
    )
    
    # Prepare output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(
        config.get('output_folder', 'audio'),
        config.get('folder_name', timestamp)
    )
    os.makedirs(output_dir, exist_ok=True)
    
    # Prepare verses list with generated filenames
    verses_with_filenames = []
    for verse_ref, verse_text in scripture.verses:
        filename = generate_filename(verse_ref, config.get('filename_config', {}))
        # Store filename without extension in CSV
        csv_filename = os.path.splitext(filename)[0]
        verses_with_filenames.append([verse_ref, verse_text, csv_filename])
    
    # Write CSV file
    csv_path = os.path.join(output_dir, f"{config.get('folder_name', timestamp)}.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['Verse Reference', 'Text', 'Audio Filename'])
        writer.writerows(verses_with_filenames)
    
    # Generate audio files - add .mp3 extension back for processing
    verses_for_processing = [
        [verse_ref, text, filename + '.mp3'] 
        for verse_ref, text, filename in verses_with_filenames
    ]
    
    process_verses(
        verses_for_processing,
        output_dir=output_dir,
        voice=config.get('voice', os.getenv('DEFAULT_VOICE')),
        api_key=os.getenv('ELEVENLABS_API_KEY')
    )
    
    return csv_path, output_dir

# Example usage
if __name__ == "__main__":
    config = {
        'translation': 'jpn-jpn1965',
        'output_folder': 'audio',
        'folder_name': 'luke_2_jpn',
        'filename_config': {
            'prefix': 'bible',
            'include_verse_name': True,
            'include_uuid': False,
            'suffix': 'jp'
        },
        'voice': 'George'
    }
    
    csv_path, output_dir = generate_bible_audio(
        'Luke 2:1',
        'Luke 2:2',
        config
    )
    
    print(f"Generated audio files in: {output_dir}")
    print(f"CSV file created at: {csv_path}") 