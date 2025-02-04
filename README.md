# Bible Audio Generator

Generate high-quality audio files from Bible verses using ElevenLabs text-to-speech API.

## Quick Start

1. **Install Dependencies**
```bash
pip install elevenlabs python-dotenv beautifulsoup4 requests
```

2. **Set Up Environment**
Create a `.env` file in the project root:

```
ELEVENLABS_API_KEY=your_api_key_here
DEFAULT_VOICE=George
DEFAULT_TRANSLATION=eng-web
```

3. **Basic Usage**
```python
config = {
'translation': 'eng-web', # e-bible translation code
'output_folder': 'audio', # base output folder
'folder_name': 'john_3', # subfolder name (also used for CSV)
'filename_config': {
'prefix': 'bible', # optional prefix for files
'include_verse_name': True, # include verse reference in filename
'include_uuid': False, # add unique identifier
'suffix': 'en' # optional suffix
},
'voice': 'George' # ElevenLabs voice
}
csv_path, output_dir = generate_bible_audio(
'John 3:16', # start verse
'John 3:18', # end verse
config
)
```

## Output

- Creates MP3 files for each verse
- Generates a CSV file with:
  - Verse references
  - Original text
  - Audio filenames

## Available Translations

Common codes:
- `eng-web` (World English Bible)
- `spa-spabes` (Spanish Bible)
- `jpn-jpn1965` (Japanese Bible 1965)

See [reference.md](reference.md) for all available translations, voices, and languages.

## Configuration Options

- `translation`: eBible translation code
- `output_folder`: Base directory for audio files
- `folder_name`: Subfolder name (also used for CSV filename)

- `filename_config`:
  - `prefix`: Add prefix to filenames
  - `include_verse_name`: Include verse reference (e.g., "JOHN_3_16")
  - `include_uuid`: Add unique identifier
  - `suffix`: Add suffix to filenames
- `voice`: ElevenLabs voice name

## Requirements

- Python 3.7+
- [ElevenLabs API key](elevenlabs.io)
  - [Pricing](https://elevenlabs.io/pricing)
- Internet connection (for eBible corpus access)
