# Project Cloner

The `clone_project.py` script allows you to clone an existing project in the database with all its quests, assets, and relationships, while changing the target language.

## Features

- Clones an entire project structure including:
  - All quests with their names and descriptions
  - All assets with their content (text only, not audio)
  - All tag relationships (quest-tag and asset-tag links)
  - All quest-asset relationships
- Creates or reuses target languages
- Maintains a session record for rollback capability
- Supports deletion of cloned projects if needed

## Usage

### Basic Cloning

1. Create a configuration JSON file (see `config_clone_example.json`):

```json
{
  "source_project_name": "Frases Português Brasileiro",
  "target_language_native_name": "Yanomami",
  "new_project_description": "Coleção de frases traduzidas para Yanomami",
  
  // Optional fields:
  "new_project_name": "Frases Yanomami",  // Defaults to "SourceName (Clone)"
  "target_language_english_name": "Yanomami",
  "target_language_iso639_3": "und",
  "target_language_locale": "",
  "target_language_ui_ready": false,
  "private": false
}
```

2. Run the clone script:

```bash
python clone_project.py config_clone.json
```

### Configuration Fields

#### Required Fields

- `source_project_name`: The exact name of the project to clone
- `target_language_native_name`: Native name of the target language
- `new_project_description`: Description for the new cloned project

#### Optional Fields

- `new_project_name`: Name for the new project (defaults to source name + " (Clone)")
- `target_language_english_name`: English name of the target language
- `target_language_iso639_3`: ISO 639-3 code for the language (defaults to "und" for undetermined)
- `target_language_locale`: Locale code (e.g., "pt-BR")
- `target_language_ui_ready`: Whether the language is ready for UI display
- `private`: Whether the new project should be private

### Session Records

Every clone operation creates a session record file in the `session_records/` directory with the format:
`clone_session_record_YYYYMMDD_HHMMSS.json`

This file contains:
- Timestamp of the operation
- Source project name
- All created database records (languages, projects, quests, assets, links)

### Deleting a Cloned Project

If you need to delete a cloned project (e.g., due to an error or for testing), use the session record:

```bash
python clone_project.py --delete session_records/clone_session_record_20240115_143022.json
```

This will:
- Delete all created records in reverse order
- Handle foreign key constraints properly
- Only delete records created during that specific clone session

## Important Notes

1. **Audio files are NOT cloned** - The new project will have all the text content but no audio files. You'll need to generate new audio for the target language.

2. **Language reuse** - If a language with the same native name already exists, it will be reused rather than creating a duplicate.

3. **Project name uniqueness** - The script will fail if a project with the new name already exists.

4. **Tags are shared** - Tags are not duplicated; the cloned project uses the same tags as the source.

5. **Source language preserved** - The source language of assets remains the same as in the original project.

6. **Large projects** - The script handles large projects with thousands of assets by:
   - Fetching quest-asset links individually for each quest to avoid Supabase's 1000-row query limit
   - Using pagination for projects with more than 1000 quests
   - Implementing automatic retry logic for connection errors
   - Resetting connections periodically to avoid HTTP/2 stream limits
   - Providing progress updates during long-running operations

## Example Workflow

1. Clone a Portuguese project for Yanomami translation:

```bash
python clone_project.py config_clone_yanomami.json
```

2. If something goes wrong, check the session record:

```bash
ls session_records/
# Find the latest clone_session_record_*.json file
```

3. Delete the cloned project if needed:

```bash
python clone_project.py --delete session_records/clone_session_record_20240115_143022.json
```

## Error Handling

The script includes comprehensive error handling:
- Validates all required configuration fields
- Checks if source project exists
- Prevents duplicate project names
- Saves session records even if the operation fails
- Provides detailed logging of all operations

## Integration with Existing Tools

After cloning a project, you can:
1. Use the unified content processor to add audio to the cloned project
2. Use the existing upload tools to manage the content
3. View and manage the project through your Supabase dashboard

## Session Record Analysis Tools

Two additional scripts are provided for analyzing session records:

### analyze_session_record.py

Analyzes a single session record file and provides detailed statistics:

```bash
python analyze_session_record.py session_records/clone_session_record_20240115_143022.json
```

Output includes:
- Total records created by table
- Breakdown of quests by project
- Asset type analysis
- Tag creation summary

### analyze_all_sessions.py

Provides a summary of all session records in the `session_records/` directory:

```bash
python analyze_all_sessions.py
```

Output includes:
- Sessions grouped by operation type
- Total records across all sessions
- Aggregate statistics by table
- Error reporting for corrupted files