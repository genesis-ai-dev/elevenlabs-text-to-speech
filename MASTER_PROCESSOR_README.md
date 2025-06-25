# Master Scripture Processor

The `master_scripture_processor.py` is a comprehensive tool that orchestrates scripture reference extraction, Supabase database uploads, and audio generation using either ElevenLabs or OpenAI text-to-speech APIs.

## Features

- **Scripture Reference Processing**: Uses `ScriptureReference.py` to extract verses from various Bible formats
- **Supabase Integration**: Creates projects, quests, assets, and manages all relationships
- **Audio Generation**: Optionally generates M4A audio files using ElevenLabs v3 API or OpenAI TTS
- **Flexible Audio Storage**: Supports saving audio files locally, to database, or both
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
    "provider": "openai",
    "save_local": true,
    "save_to_database": true,
    
    "elevenlabs": {
      "voice_id": "your-elevenlabs-voice-id"
    },
    
    "openai": {
      "voice": "echo",
      "model": "gpt-4o-mini-tts",
      "instructions": "Voice instructions for OpenAI TTS"
    }
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
- The `languages` key in the project file is optional - if omitted, languages will be fetched from the database as needed

#### `scripture_reference`
- `bible_filename`: Path to the Bible text file
- `source_type`: One of `"ebible"`, `"local_ebible"`, `"usfm"`, `"xhtml"`
- `versification`: Versification system (default: `"eng"`)

#### `audio_generation`
- `provider`: Choose between `"elevenlabs"` or `"openai"` for TTS provider
- `save_local`: Boolean to save audio files locally in `generated_audio/{project_name}/`
- `save_to_database`: Boolean to upload audio files to Supabase storage
- `elevenlabs`: Configuration for ElevenLabs provider
  - `voice_id`: ElevenLabs voice ID to use for generation
- `openai`: Configuration for OpenAI provider
  - `voice`: OpenAI voice name (e.g., "echo", "nova", "shimmer", "onyx", "fable", "alloy")
  - `model`: OpenAI TTS model (default: "gpt-4o-mini-tts")
  - `instructions`: Voice instructions for pronunciation, tone, pacing, etc.

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
   # ELEVENLABS_API_KEY=your_elevenlabs_api_key (if using ElevenLabs)
   # OPENAI_API_KEY=your_openai_api_key (if using OpenAI)
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
- **Note**: Local audio files in `generated_audio/` are NOT deleted and must be removed manually if needed

## Process Flow

1. **Load Configuration**: Reads the JSON config file
2. **Initialize Clients**: Sets up Supabase and audio handler (if enabled)
3. **Process Languages**: 
   - If `languages` key exists in project data: Creates/updates languages in Supabase
   - Otherwise: Fetches existing languages from database as needed
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
- Supports both ElevenLabs v3 API and OpenAI TTS API
- Generates MP3 and converts to M4A format
- Can save audio files locally in `generated_audio/{project_name}/` directory
- Can upload to Supabase storage with filename format: `{verse_reference}_{uuid}.m4a`
- Database files are stored in `{bucket_name}/{content_folder}/` path
- Links audio file to asset via `asset_content_link.audio_id`
- Reuses existing audio files in database when available (unless `save_local` is true)

### Provider-specific features:
- **ElevenLabs**: Uses v3 API with multilingual model
- **OpenAI**: Supports custom voice instructions for pronunciation, tone, and pacing

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
    "provider": "elevenlabs",
    "save_local": false,
    "save_to_database": false
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

### Full audio generation with Portuguese book names (ElevenLabs):
```json
{
  "project_file": "json_projects/john_quests_ch_1.json",
  "scripture_reference": {
    "bible_filename": "source_texts/brazilian_portuguese_translation_4_corrected.txt",
    "source_type": "local_ebible"
  },
  "audio_generation": {
    "provider": "elevenlabs",
    "save_local": true,
    "save_to_database": true,
    "elevenlabs": {
      "voice_id": "JBFqnCBsd6RMkjVDRZzb"
    }
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

### Audio generation with OpenAI TTS:
```json
{
  "project_file": "json_projects/john_quests_ch_1.json",
  "scripture_reference": {
    "bible_filename": "source_texts/brazilian_portuguese_translation_4_corrected.txt",
    "source_type": "local_ebible"
  },
  "audio_generation": {
    "provider": "openai",
    "save_local": true,
    "save_to_database": true,
    "openai": {
      "voice": "echo",
      "model": "gpt-4o-mini-tts",
      "instructions": "Voice affect: Calm, composed, reverent, and trustworthy.\n\nTone: Sincere, respectable, and even.\n\nPacing: Steady and consistent for narration.\n\nPronunciation: Clear, precise Brazilian-Portuguese."
    }
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