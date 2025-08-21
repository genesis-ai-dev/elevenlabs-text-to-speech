# Unified Content Processor

A modular system for processing different types of content (Bible verses, line-based text) and uploading to Supabase with optional audio generation.

## Features

- **Multiple Content Types**: Supports Bible verses and line-based content
- **Modular Architecture**: Clean separation of concerns with dedicated handlers
- **Audio Generation**: Optional TTS using OpenAI, ElevenLabs, or Google Cloud TTS
- **Concurrent Processing**: Efficient parallel audio generation
- **Flexible Configuration**: JSON-based configuration for easy customization
- **Session Recording**: Tracks all database operations for rollback capability

## Architecture

```
unified_content_processor.py     # Main orchestrator
├── content_handlers/           # Content type handlers
│   ├── base.py                # Abstract base class
│   ├── bible.py               # Bible verse handler
│   └── lines.py               # Line-based content handler
├── supabase_handler.py        # Database operations
└── audio_handler.py           # Audio generation (existing)
```

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

### Bible Content Configuration

```json
{
  "content_type": "bible",
  
  "project_files": [
    "json_projects/rom_pt-BR.json"
  ],
  
  "scripture_reference": {
    "bible_filename": "source_texts/brazilian_portuguese_translation_6.txt",
    "source_type": "local_ebible",
    "versification": "eng"
  },
  
  "audio_generation": {
    "provider": "openai",
    "save_local": false,
    "save_to_database": true,
    "max_concurrent_requests": 10,
    "requests_per_minute": 40
  },
  
  "book_abbreviations": {
    "use_localized": true,
    "language": "pt-BR"
  },
  
  "tag_labels": {
    "book": "livro",
    "chapter": "capítulo",
    "verse": "versículo"
  }
}
```

### Line-Based Content Configuration

```json
{
  "content_type": "lines",
  
  "project_files": [
    "json_projects/lines_project.json"
  ],
  
  "lines_reference": {
    "source_file": "source_texts/sentences.txt",
    "group_size": 100
  },
  
  "audio_generation": {
    "provider": "openai",
    "save_local": true,
    "save_to_database": true
  },
  
  "tag_labels": {
    "line": "linha",
    "group": "grupo"
  }
}
```

## Project File Format

### Bible Project

```json
{
  "projects": [{
    "name": "Bíblia",
    "source_language_english_name": "Brazilian Portuguese",
    "target_language_english_name": "Yanomami",
    "quests": [{
      "name": "Romanos Capítulo 1",
      "verse_ranges": [
        ["Rom 1:1", "Rom 1:32"]
      ],
      "additional_tags": ["misión:1047"]
    }]
  }]
}
```

### Lines Project

```json
{
  "projects": [{
    "name": "Frases Exemplo",
    "source_language_english_name": "Brazilian Portuguese",
    "target_language_english_name": "Yanomami",
    "quests": [{
      "name": "Frases 1-100",
      "line_ranges": [
        [1, 100]
      ],
      "additional_tags": ["módulo:1", "iniciante"]
    }]
  }]
}
```

## Usage

```bash
# Process Bible content
python unified_content_processor.py config_pt-BR_bible.json

# Process line-based content
python unified_content_processor.py config_lines_example.json

# Delete a session (rollback)
python unified_content_processor.py --delete session_records/session_record_20240115_143022.json
```

## Session Recording

Every processing run creates a session record file in the `session_records/` directory. This file tracks all database operations performed during the session:

- Languages created/updated
- Projects created/updated
- Quests created/updated
- Assets created
- Content links created
- Tags created
- Tag links created
- Audio files uploaded to storage
- Local audio files generated

### Session File Format

```json
{
  "timestamp": "20240115_143022",
  "languages": [
    {"id": "uuid", "english_name": "Brazilian Portuguese", "iso639_3": "por"}
  ],
  "projects": [
    {"id": "uuid", "name": "Bíblia", "source_language_id": "uuid", "target_language_id": "uuid"}
  ],
  "quests": [
    {"id": "uuid", "name": "Romanos Capítulo 1", "project_id": "uuid"}
  ],
  "assets": [
    {"id": "uuid", "name": "Romanos 1:1", "source_language_id": "uuid"}
  ],
  "audio_files": [
    {"id": "path", "bucket": "assets", "path": "content/filename.m4a"}
  ],
  "local_audio_files": [
    {"id": "path", "path": "generated_audio/project/filename.m4a", "reference": "ROM_1_1"}
  ]
}
```

### Rollback/Deletion

To undo all operations from a session:

```bash
python unified_content_processor.py --delete session_records/session_record_YYYYMMDD_HHMMSS.json
```

This will:
1. Delete audio files from Supabase storage
2. Delete local audio files
3. Remove all database records created during the session
4. Preserve shared resources (languages, tags) that might be used elsewhere

## Content Handlers

### Bible Content Handler
- Uses `ScriptureReference` class to extract verses
- Supports localized book names
- Creates tags for book, chapter, and verse

### Lines Content Handler
- Reads lines from a text file
- Supports line ranges (e.g., 1-100, 101-200)
- Creates tags for line number and optional group
- Assets named by line number (1, 2, 3, etc.)

## Database Schema

The system works with the following Supabase tables:
- `language`: Language definitions
- `project`: Translation projects
- `quest`: Quest/lesson definitions
- `asset`: Individual content items (verses or lines)
- `asset_content_link`: Text and audio content
- `tag`: Tag definitions
- Various link tables for many-to-many relationships

## Audio Generation

Supports four providers:
- **OpenAI**: Uses the TTS API with configurable `voice` and `model`
- **ElevenLabs**: Uses the v3 API with configurable `voice_id`
- **Google Cloud TTS**: Uses Google Cloud Text-to-Speech with configurable `language_code`, `voice_name`, `ssml_gender`, `speaking_rate`, `pitch`, `volume_gain_db`, and `audio_encoding`
- **Hugging Face (custom endpoint)**: Calls your Hugging Face Inference Endpoint (Custom task) which hosts a `handler.py` that returns base64 WAV for MMS TTS.

General options under `audio_generation`:
- `provider`: `openai` | `elevenlabs` | `google`
- `save_local`: Save generated m4a locally in `generated_audio/<project>/`
- `save_to_database`: Upload to Supabase storage
- `max_concurrent_requests`: Concurrency limiter across providers
- `requests_per_minute`: Adaptive rate limiting
- `reuse_existing_audio`: If true and `save_to_database` is true, reuse matching audio already in storage

Provider-specific options:
- `openai`:
  - `voice` (e.g., `onyx`, `alloy`, ...)
  - `model` (default `gpt-4o-mini-tts`)
- `elevenlabs`:
  - `voice_id` (required)
- `google`:
  - `language_code` (e.g., `en-US`, `id-ID`)
  - `voice_name` (e.g., `en-US-Neural2-C`, optional)
  - `ssml_gender` (`MALE` | `FEMALE` | `NEUTRAL`)
  - `speaking_rate` (float, default 1.0)
  - `pitch` (float semitones, default 0.0)
  - `volume_gain_db` (float dB, default 0.0)
  - `audio_encoding` (`MP3` | `OGG_OPUS` | `LINEAR16`)
 - `huggingface`:
  - Uses environment variables only (no extra JSON fields)
  - Requires a Custom Inference Endpoint URL and Read token

### Hugging Face setup

1. Create a model repository with a `handler.py` that implements `EndpointHandler` and returns a JSON payload with `audio_base64` and `sampling_rate`. Also include a `requirements.txt` with dependencies. See: https://huggingface.co/docs/inference-endpoints/guides/custom_handler
2. Deploy as an Inference Endpoint with Container Type: Default and Task: Custom. From the repo page, click “Deploy to Inference Endpoints” so the repository is pre-filled.
3. Copy the Endpoint URL from the endpoint Overview.
4. Set environment variables:

```bash
# Windows PowerShell (current session)
$env:HF_TTS_ENDPOINT = "https://<your-endpoint>.endpoints.huggingface.cloud"
$env:HF_TOKEN_READ = "hf_..."
```

or add to `.env` in project root:

```env
HF_TTS_ENDPOINT=https://<your-endpoint>.endpoints.huggingface.cloud
HF_TOKEN_READ=hf_...
```

5. In your config JSON, set:

```json
"audio_generation": {
  "provider": "huggingface",
  "save_local": true,
  "save_to_database": false
}
```

This provider will POST `{ "inputs": "..." }` to `HF_TTS_ENDPOINT`, decode `audio_base64` WAV, and export `.m4a`.

Authentication:
- OpenAI: set `OPENAI_API_KEY`
- ElevenLabs: set `ELEVENLABS_API_KEY`
- Google: set `GOOGLE_APPLICATION_CREDENTIALS` to a service account JSON path or use ADC
- Hugging Face: set `HF_TTS_ENDPOINT` and `HF_TOKEN_READ`

### Google Cloud TTS Setup (Service Account JSON)

1. Enable the API
   - In the Google Cloud Console, select your project
   - Go to “APIs & Services” → “Library”
   - Search for “Text-to-Speech API” and click “Enable”

2. Create a Service Account
   - Go to “IAM & Admin” → “Service Accounts” → “Create service account”
   - Provide a name (e.g., `tts-service`) and click “Create and continue”
   - Grant a role with TTS permissions (e.g., “Cloud Text-to-Speech API User” or an appropriate role with least privilege)
   - Click “Done”

3. Create and download the key (JSON)
   - Open the service account → “Keys” tab → “Add key” → “Create new key” → JSON → Download the file
   - Store it somewhere secure (e.g., `C:\keys\gcp-tts.json` on Windows, `~/keys/gcp-tts.json` on macOS)

4. Set the environment variable
   - Windows (PowerShell):
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\\keys\\gcp-tts.json"
# Persist for future shells (requires new terminal):
setx GOOGLE_APPLICATION_CREDENTIALS "C:\\keys\\gcp-tts.json"
```
   - macOS (zsh):
```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/keys/gcp-tts.json"
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/keys/gcp-tts.json"' >> ~/.zshrc
source ~/.zshrc
```

5. Optional: Use Application Default Credentials (ADC) instead of a key file
```bash
gcloud auth application-default login
```
This will configure credentials for the current user on the machine; no JSON path is required.

6. Quick test
   - Run the sample at `general_helper_scripts/google_tts.py` after setting credentials. It should create `output_id.mp3`.

## Extending

To add a new content type:

1. Create a new handler in `content_handlers/`:
```python
from .base import ContentHandler

class MyContentHandler(ContentHandler):
    def get_content_items(self, quest_config):
        # Return list of (reference, text) tuples
        pass
    
    def format_asset_name(self, reference, language):
        # Format reference for display
        pass
    
    def get_tags(self, reference):
        # Return list of tag names
        pass
```

2. Register in `unified_content_processor.py`:
```python
elif content_type == 'mytype':
    self.content_handler = MyContentHandler(self.config)
```

3. Create appropriate configuration and project files

## Migration from Old System

The new system is backward compatible with existing Bible project files. To migrate:

1. Add `"content_type": "bible"` to your config
2. Use `unified_content_processor.py` instead of the old scripts
3. All existing features are preserved

## Performance

- Concurrent audio generation (configurable max requests)
- Rate limiting support for API calls
- Efficient batch processing
- Reuses existing audio when available 