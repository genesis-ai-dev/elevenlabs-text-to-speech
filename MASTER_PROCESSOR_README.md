# Master Scripture Processor

The `master_scripture_processor.py` is a comprehensive tool that orchestrates scripture reference extraction, Supabase database uploads, and audio generation using ElevenLabs v3 API.

## Features

- **Scripture Reference Processing**: Uses `ScriptureReference.py` to extract verses from various Bible formats
- **Supabase Integration**: Creates projects, quests, assets, and manages all relationships
- **Audio Generation**: Optionally generates M4A audio files using ElevenLabs v3 API
- **Localized Book Names**: Supports language-specific book abbreviations
- **Flexible Configuration**: JSON-based configuration for all settings
- **Session Recording**: Automatically creates timestamped record files of all database operations
- **Rollback Support**: Delete all records created in a session using the `--delete` flag

## Configuration

Create a JSON configuration file with the following structure:

```json
{
  "project_file": "path/to/project.json",
  
  "scripture_reference": {
    "bible_filename": "path/to/bible.txt",
    "source_type": "local_ebible",
    "versification": "eng"
  },
  
  "audio_generation": {
    "enabled": true,
    "voice_id": "your-elevenlabs-voice-id"
  },
  
  "book_abbreviations": {
    "use_localized": true,
    "language": "pt-BR"
  },
  
  "storage": {
    "bucket_name": "assets",
    "content_folder": "content"
  }
}
```

### Configuration Options

#### `project_file`
- Path to the JSON file containing project, quest, and verse range definitions
- Format follows the same structure as `john_quests_ch_1.json`

#### `scripture_reference`
- `bible_filename`: Path to the Bible text file
- `source_type`: One of `"ebible"`, `"local_ebible"`, `"usfm"`, `"xhtml"`
- `versification`: Versification system (default: `"eng"`)

#### `audio_generation`
- `enabled`: Boolean to enable/disable audio generation
- `voice_id`: ElevenLabs voice ID to use for generation

#### `book_abbreviations`
- `use_localized`: Boolean to enable localized book names
- `language`: Language code (`"en"` or `"pt-BR"`)

#### `storage`
- `bucket_name`: Supabase storage bucket name (default: `"assets"`)
- `content_folder`: Folder within the bucket for audio files (default: `"content"`)

## Usage

1. **Set up environment variables**:
   ```bash
   cp .env-template .env
   # Edit .env with your credentials:
   # SUPABASE_URL=your_supabase_url
   # SUPABASE_KEY=your_supabase_key
   # ELEVENLABS_API_KEY=your_elevenlabs_api_key
   ```

2. **Create your configuration file**:
   - Create a file named `config.json` in the project root
   - Or update the `CONFIG_FILE` variable in `master_scripture_processor.py` to point to your config file

3. **Run the processor**:
   ```bash
   python master_scripture_processor.py
   ```
   
   The script will look for `config.json` by default. To use a different config file, edit the `CONFIG_FILE` variable at the top of the `main()` function in `master_scripture_processor.py`.

## Session Recording and Rollback

### Session Recording
Every time you run the script, it automatically creates a timestamped session record file:
- Filename format: `session_record_YYYYMMDD_HHMMSS.json`
- Contains IDs of all created records: languages, projects, quests, assets, links, tags, and audio files
- Saved in the current directory

### Rollback/Delete
To delete all records created in a specific session:
```bash
python master_scripture_processor.py --delete session_record_20240115_143022.json
```

This will:
- Delete all database records created in that session (in reverse order to handle dependencies)
- Remove uploaded audio files from Supabase storage
- Show progress and any errors during deletion

## Process Flow

1. **Load Configuration**: Reads the JSON config file
2. **Initialize Clients**: Sets up Supabase and ElevenLabs (if enabled)
3. **Process Languages**: Creates/updates languages in Supabase
4. **Process Projects**: For each project in the JSON:
   - Creates/updates the project
   - For each quest:
     - Creates/updates the quest
     - Extracts verses using ScriptureReference
     - Creates assets for each verse
     - Optionally generates and uploads audio
     - Creates all tag relationships
     - Links assets to quests

## Audio Generation

When audio generation is enabled:
- Uses ElevenLabs v3 API (`text_to_speech.convert`)
- Generates MP3 and converts to M4A format
- Uploads to Supabase storage with filename format: `{verse_reference}_{uuid}.m4a`
- Files are stored in `{bucket_name}/{content_folder}/` path
- Links audio file to asset via `asset_content_link.audio_id`

## Book Name Localization

When localization is enabled:
- Uses `book_names.json` for language-specific abbreviations
- Supports English (`en`) and Brazilian Portuguese (`pt-BR`)
- Falls back to English book codes if localization not available

## Example Configurations

### Basic text-only upload:
```json
{
  "project_file": "json_projects/john_quests_ch_1.json",
  "scripture_reference": {
    "bible_filename": "source_texts/brazilian_portuguese_translation_4_corrected.txt",
    "source_type": "local_ebible"
  },
  "audio_generation": {
    "enabled": false
  },
  "book_abbreviations": {
    "use_localized": false
  },
  "storage": {
    "bucket_name": "assets",
    "content_folder": "content"
  }
}
```

### Full audio generation with Portuguese book names:
```json
{
  "project_file": "json_projects/john_quests_ch_1.json",
  "scripture_reference": {
    "bible_filename": "source_texts/brazilian_portuguese_translation_4_corrected.txt",
    "source_type": "local_ebible"
  },
  "audio_generation": {
    "enabled": true,
    "voice_id": "JBFqnCBsd6RMkjVDRZzb"
  },
  "book_abbreviations": {
    "use_localized": true,
    "language": "pt-BR"
  },
  "storage": {
    "bucket_name": "assets",
    "content_folder": "content"
  }
}
```

## Error Handling

- Missing environment variables will raise `RuntimeError`
- Failed audio generation logs error but continues processing
- Missing languages in database will raise `RuntimeError`
- File not found errors are logged with context 