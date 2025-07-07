# Unified Content Processor

A modular system for processing different types of content (Bible verses, line-based text) and uploading to Supabase with optional audio generation.

## Features

- **Multiple Content Types**: Supports Bible verses and line-based content
- **Modular Architecture**: Clean separation of concerns with dedicated handlers
- **Audio Generation**: Optional TTS using OpenAI or ElevenLabs
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

Supports two providers:
- **OpenAI**: Uses the TTS API with configurable voice and model
- **ElevenLabs**: Uses the v3 API with multilingual support

Audio files are:
- Generated concurrently for efficiency
- Optionally saved locally in `generated_audio/`
- Optionally uploaded to Supabase storage
- Reused if matching audio already exists

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