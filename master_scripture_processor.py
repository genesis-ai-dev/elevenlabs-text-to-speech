#!/usr/bin/env python3
"""
Master Scripture Processor
Coordinates scripture reference extraction, Supabase uploads, and audio generation
"""

import os
import json
import uuid
import sys
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client
from pydub import AudioSegment
import io
import logging
import time

from ScriptureReference import ScriptureReference
from supabase_upload_quests import (
    get_supabase_client, 
    load_book_names,
    get_localized_book_name,
    upsert_language,
    upsert_project,
    get_or_create_tag
)
from audio_handler import AudioHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionRecorder:
    """Records all database operations for potential rollback"""
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"session_record_{self.timestamp}.json"
        self.filepath = None
        self.records = {
            "timestamp": self.timestamp,
            "languages": [],
            "projects": [],
            "quests": [],
            "assets": [],
            "asset_content_links": [],
            "quest_asset_links": [],
            "asset_tag_links": [],
            "quest_tag_links": [],
            "tags": [],
            "audio_files": [],
            "local_audio_files": []
        }
        # Initialize the file immediately
        self._initialize_file()
    
    def _initialize_file(self):
        """Initialize the session record file"""
        # Ensure session_records directory exists
        os.makedirs('session_records', exist_ok=True)
        
        # Set filepath
        self.filepath = os.path.join('session_records', self.filename)
        
        # Create initial file
        self._write_to_file()
        logger.info(f"Session record initialized: {self.filepath}")
    
    def _write_to_file(self):
        """Write current records to file"""
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2)
    
    def add_record(self, table: str, record_id: str, additional_info: dict = None):
        """Add a record to the session and save immediately"""
        record = {"id": record_id}
        if additional_info:
            record.update(additional_info)
        
        if table in self.records:
            self.records[table].append(record)
            # Save after each addition
            self._write_to_file()
    
    def save(self):
        """Final save of the session record to file"""
        self._write_to_file()
        print(f"\nSession record saved to: {self.filepath}")
        return self.filepath


class MasterScriptureProcessor:
    def __init__(self, config_file: str, session_recorder: SessionRecorder = None):
        """Initialize with configuration from JSON file"""
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Load environment variables
        load_dotenv()
        
        # Initialize clients
        self.supabase = get_supabase_client()
        
        # Initialize session recorder
        self.session_recorder = session_recorder
        
        # Initialize audio handler if audio generation is enabled
        audio_config = self.config.get('audio_generation', {})
        if audio_config.get('save_local', False) or audio_config.get('save_to_database', False):
            self.audio_handler = AudioHandler(self.config)
        else:
            self.audio_handler = None
        
        # Load book names if localization is enabled
        self.book_names_data = {}
        if self.config.get('book_abbreviations', {}).get('use_localized', False):
            self.book_names_data = load_book_names()
    
    def upload_audio_to_storage(self, file_path: str, storage_path: str, bucket_name: str) -> Optional[str]:
        """Upload audio file to Supabase storage"""
        try:
            with open(file_path, 'rb') as f:
                response = self.supabase.storage.from_(bucket_name).upload(
                    storage_path,
                    f.read(),
                    file_options={"content-type": "audio/mpeg"}
                )
            
            # Get public URL
            public_url = self.supabase.storage.from_(bucket_name).get_public_url(storage_path)
            return public_url
            
        except Exception as e:
            logger.error(f"Error uploading audio to storage: {str(e)}")
            return None
    
    async def process_verses_async(self, verses: List[Tuple[str, str]], project_info: Dict, 
                                  lang_map: Dict, tag_cache: Dict, project_id: str, quest_id: str) -> None:
        """Process verses for a quest, creating assets and optionally generating audio concurrently"""
        
        audio_config = self.config.get('audio_generation', {})
        save_local = audio_config.get('save_local', False)
        save_to_database = audio_config.get('save_to_database', False)
        generate_audio = save_local or save_to_database
        
        book_abbr_config = self.config.get('book_abbreviations', {})
        use_localized = book_abbr_config.get('use_localized', False)
        abbr_language = book_abbr_config.get('language', 'en')
        
        source_lang_id = lang_map[project_info['source_language_english_name']]
        
        # Prepare batch for audio generation
        audio_batch = []
        verse_metadata = {}
        
        for verse_ref, verse_text in verses:
            # Parse reference
            book_code, chapter, verse = verse_ref.split('_', 2)
            
            # Get formatted book name
            if use_localized:
                formatted_book = get_localized_book_name(
                    book_code, 
                    project_info['source_language_english_name'], 
                    self.book_names_data
                )
            else:
                formatted_book = book_code.title()
            
            formatted_name = f"{formatted_book} {chapter}:{verse}"
            
            # Check if asset exists for this quest
            existing_asset = self.supabase.table('quest_asset_link') \
                .select('asset_id, asset(id, name)') \
                .eq('quest_id', quest_id) \
                .execute()
            
            asset_id = None
            for link in existing_asset.data:
                if link['asset']['name'] == formatted_name:
                    asset_id = link['asset_id']
                    break
            
            if not asset_id:
                # Asset not linked to this quest, create new one
                aresp = self.supabase.table('asset') \
                    .insert({
                        'name': formatted_name,
                        'source_language_id': source_lang_id,
                        'created_at': datetime.now(timezone.utc).isoformat()
                    }, returning='representation') \
                    .execute()
                asset_id = aresp.data[0]['id']
                
                # Record the creation
                if self.session_recorder:
                    self.session_recorder.add_record('assets', asset_id, {'name': formatted_name})
            
            # Store metadata for later use
            verse_metadata[verse_ref] = {
                'asset_id': asset_id,
                'formatted_name': formatted_name,
                'verse_text': verse_text,
                'formatted_book': formatted_book,
                'chapter': chapter,
                'verse': verse
            }
            
            # Prepare audio generation if needed
            if generate_audio and self.audio_handler:
                # Get storage configuration
                storage_config = self.config.get('storage', {})
                bucket_name = storage_config.get('bucket_name', 'assets')
                content_folder = storage_config.get('content_folder', 'content')
                
                # Get project name for local storage
                project_name = project_info.get('name', 'default').replace(' ', '_')
                
                # Get provider-specific voice info
                provider = audio_config.get('provider', 'openai')
                if provider == 'openai':
                    voice = audio_config.get('openai', {}).get('voice', 'onyx')
                elif provider == 'elevenlabs':
                    voice = audio_config.get('elevenlabs', {}).get('voice_id', 'default')
                else:
                    voice = 'default'
                
                # Get language code (use ISO code if available, otherwise use English name)
                lang_code = project_info.get('source_language_iso_code', project_info['source_language_english_name'])
                
                # Check if we should save to database and if audio already exists
                audio_id = None
                reuse_existing = audio_config.get('reuse_existing_audio', True)
                
                if save_to_database and reuse_existing:
                    # Look for existing audio with matching verse_ref, language, and voice
                    existing_audio = self.supabase.table('asset_content_link') \
                        .select('audio_id') \
                        .like('audio_id', f'{content_folder}/{verse_ref}_{lang_code}_{voice}_%') \
                        .limit(1) \
                        .execute()
                    
                    if existing_audio.data and existing_audio.data[0]['audio_id']:
                        # Reuse existing audio file
                        audio_id = existing_audio.data[0]['audio_id']
                        logger.info(f"Reusing existing audio for {verse_ref} ({lang_code}, {voice}): {audio_id}")
                        verse_metadata[verse_ref]['audio_id'] = audio_id
                
                # Add to batch if no existing audio
                if not audio_id:
                    file_uuid = str(uuid.uuid4())
                    filename = f"{verse_ref}_{lang_code}_{voice}_{file_uuid}.m4a"
                    
                    # Determine output path
                    if save_local:
                        # Create local directory structure
                        local_dir = os.path.join("generated_audio", project_name)
                        os.makedirs(local_dir, exist_ok=True)
                        local_path = os.path.join(local_dir, filename)
                    else:
                        # Use temp file for database upload only
                        local_path = f"temp_{asset_id}.m4a"
                    
                    audio_batch.append((verse_text, local_path))
                    verse_metadata[verse_ref]['pending_audio'] = {
                        'local_path': local_path,
                        'filename': filename,
                        'save_local': save_local,
                        'save_to_database': save_to_database
                    }
        
        # Generate audio in parallel if needed
        if audio_batch and self.audio_handler:
            logger.info(f"Generating {len(audio_batch)} audio files concurrently...")
            audio_results = await self.audio_handler.generate_multiple_audio(audio_batch)
            
            # Process audio results
            for output_path, success in audio_results:
                # Find the corresponding verse
                for verse_ref, metadata in verse_metadata.items():
                    if 'pending_audio' in metadata and metadata['pending_audio']['local_path'] == output_path:
                        if success:
                            pending = metadata['pending_audio']
                            
                            # Record local file if saved
                            if pending['save_local'] and self.session_recorder:
                                self.session_recorder.add_record('local_audio_files', output_path, {
                                    'path': output_path,
                                    'verse_ref': verse_ref
                                })
                            
                            # Upload to database if configured
                            if pending['save_to_database']:
                                storage_config = self.config.get('storage', {})
                                bucket_name = storage_config.get('bucket_name', 'assets')
                                content_folder = storage_config.get('content_folder', 'content')
                                
                                storage_path = f"{content_folder}/{pending['filename']}"
                                audio_url = self.upload_audio_to_storage(output_path, storage_path, bucket_name)
                                if audio_url:
                                    metadata['audio_id'] = storage_path
                                    logger.info(f"Uploaded audio for {verse_ref}: {storage_path}")
                                    
                                    # Record the audio file creation
                                    if self.session_recorder:
                                        self.session_recorder.add_record('audio_files', storage_path, {
                                            'bucket': bucket_name,
                                            'path': storage_path
                                        })
                            
                            # Clean up temp file if not saving locally
                            if not pending['save_local'] and os.path.exists(output_path):
                                os.remove(output_path)
                        else:
                            logger.error(f"Failed to generate audio for {verse_ref}")
                        break
        
        # Now process all database updates
        for verse_ref, metadata in verse_metadata.items():
            asset_id = metadata['asset_id']
            verse_text = metadata['verse_text']
            audio_id = metadata.get('audio_id')
            
            # Check if content link already exists
            existing_content = self.supabase.table('asset_content_link') \
                .select('id') \
                .eq('asset_id', asset_id) \
                .execute()
            
            if existing_content.data:
                # Update existing content link
                self.supabase.table('asset_content_link') \
                    .update({
                        'text': verse_text,
                        'audio_id': audio_id
                    }) \
                    .eq('asset_id', asset_id) \
                    .execute()
            else:
                # Create new content link
                resp = self.supabase.table('asset_content_link') \
                    .insert({
                        'asset_id': asset_id,
                        'text': verse_text,
                        'audio_id': audio_id
                    }, returning='representation') \
                    .execute()
                
                # Record the creation
                if self.session_recorder and resp.data:
                    self.session_recorder.add_record('asset_content_links', resp.data[0]['id'], {
                        'asset_id': asset_id
                    })
            
            # Get tag labels from config
            tag_labels = self.config.get('tag_labels', {
                'book': 'book',
                'chapter': 'chapter',
                'verse': 'verse'
            })
            
            # Add tags
            for tag_name in (
                f"{tag_labels['book']}:{metadata['formatted_book']}",
                f"{tag_labels['chapter']}:{metadata['chapter']}",
                f"{tag_labels['verse']}:{metadata['verse']}"
            ):
                tag_id = get_or_create_tag(self.supabase, tag_cache, tag_name)
                
                # Check if link exists
                existing = self.supabase.table('asset_tag_link') \
                    .select('asset_id') \
                    .eq('asset_id', asset_id) \
                    .eq('tag_id', tag_id) \
                    .execute()
                
                if not existing.data:
                    self.supabase.table('asset_tag_link') \
                        .insert({
                            'asset_id': asset_id,
                            'tag_id': tag_id
                        }) \
                        .execute()
                    
                    # Record the creation
                    if self.session_recorder:
                        self.session_recorder.add_record('asset_tag_links', f"{asset_id}_{tag_id}", {
                            'asset_id': asset_id,
                            'tag_id': tag_id
                        })
    
    def process_verses(self, verses: List[Tuple[str, str]], project_info: Dict, 
                      lang_map: Dict, tag_cache: Dict, project_id: str, quest_id: str) -> None:
        """Sync wrapper for process_verses_async"""
        asyncio.run(self.process_verses_async(verses, project_info, lang_map, tag_cache, project_id, quest_id))
    
    def run(self):
        """Main execution method"""
        # Record start time
        start_time = time.time()
        
        # Get project files - support both single file and array
        project_files = []
        if 'project_file' in self.config:
            # Single file (backward compatibility)
            project_files = [self.config['project_file']]
        elif 'project_files' in self.config:
            # Array of files
            project_files = self.config['project_files']
        else:
            raise ValueError("Configuration must contain either 'project_file' or 'project_files'")
        
        # Process each project file
        for project_file in project_files:
            print(f"\n{'='*60}")
            print(f"Processing project file: {project_file}")
            print(f"{'='*60}\n")
            
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            self._process_project_data(project_data)
        
        # Calculate and display total time
        end_time = time.time()
        total_time = end_time - start_time
        
        # Format time nicely
        if total_time < 60:
            time_str = f"{total_time:.2f} seconds"
        elif total_time < 3600:
            minutes = total_time / 60
            time_str = f"{minutes:.2f} minutes ({total_time:.2f} seconds)"
        else:
            hours = total_time / 3600
            minutes = (total_time % 3600) / 60
            time_str = f"{hours:.2f} hours ({int(hours)}h {int(minutes)}m {total_time:.2f}s)"
        
        print(f"\nAll projects processed!")
        print(f"Total execution time: {time_str}")
    
    def _process_project_data(self, project_data):
        """Process a single project data object"""
        
        # Scripture reference configuration
        scripture_config = self.config.get('scripture_reference', {})
        
        # Process languages
        lang_map = {}
        
        # Process languages from project data if provided
        if 'languages' in project_data:
            for lang in project_data['languages']:
                lang_id = upsert_language(self.supabase, lang)
                lang_map[lang['english_name']] = lang_id
        
        # Fetch any additional languages from DB (including all languages if none provided)
        for proj in project_data['projects']:
            for lang_name in (proj['source_language_english_name'], proj['target_language_english_name']):
                if lang_name not in lang_map:
                    # Try to fetch from database
                    resp = self.supabase.table('language') \
                        .select('id') \
                        .eq('english_name', lang_name) \
                        .execute()
                    
                    if resp.data:
                        # Language exists in database
                        lang_map[lang_name] = resp.data[0]['id']
                        print(f"Using existing language from database: {lang_name}")
                    else:
                        # Language not found in database
                        raise RuntimeError(
                            f"Language '{lang_name}' not found in database. "
                            f"Either add it to the 'languages' section in your project file, "
                            f"or ensure it exists in the database."
                        )
        
        # Process projects and quests
        tag_cache = {}
        for proj in project_data['projects']:
            project_id = upsert_project(self.supabase, proj, lang_map)
            
            for quest in proj['quests']:
                # Check if quest exists for this project
                qresp = self.supabase.table('quest') \
                    .select('id') \
                    .eq('name', quest['name']) \
                    .eq('project_id', project_id) \
                    .execute()
                
                if qresp.data:
                    quest_id = qresp.data[0]['id']
                    print(f"Using existing quest: {quest['name']} ({quest_id})")
                else:
                    # Create new quest
                    qresp = self.supabase.table('quest') \
                        .insert({
                            'name': quest['name'],
                            'description': quest.get('description', ''),
                            'project_id': project_id
                        }, returning='representation') \
                        .execute()
                    quest_id = qresp.data[0]['id']
                    print(f"Created new quest: {quest['name']} ({quest_id})")
                    
                    # Record the creation
                    if self.session_recorder:
                        self.session_recorder.add_record('quests', quest_id, {
                            'name': quest['name'],
                            'project_id': project_id
                        })
                
                # Process verse ranges
                all_verses = []
                for start_ref, end_ref in quest.get('verse_ranges', []):
                    print(f"Processing {start_ref} to {end_ref}")
                    
                    # Create ScriptureReference with config
                    sr = ScriptureReference(
                        start_ref, 
                        end_ref,
                        bible_filename=scripture_config.get('bible_filename', 'eng-engwmbb'),
                        source_type=scripture_config.get('source_type', 'ebible'),
                        versification=scripture_config.get('versification', 'eng')
                    )
                    
                    all_verses.extend(sr.verses)
                
                # Process all verses for this quest
                self.process_verses(all_verses, proj, lang_map, tag_cache, project_id, quest_id)
                
                # Link assets to quest
                for verse_ref, _ in all_verses:
                    book_code, chapter, verse = verse_ref.split('_', 2)
                    
                    # Get formatted book name (same logic as in process_verses)
                    book_abbr_config = self.config.get('book_abbreviations', {})
                    if book_abbr_config.get('use_localized', False):
                        formatted_book = get_localized_book_name(
                            book_code, 
                            proj['source_language_english_name'], 
                            self.book_names_data
                        )
                    else:
                        formatted_book = book_code.title()
                    
                    formatted_name = f"{formatted_book} {chapter}:{verse}"
                    
                    # Find asset
                    aresp = self.supabase.table('asset') \
                        .select('id') \
                        .eq('name', formatted_name) \
                        .eq('source_language_id', lang_map[proj['source_language_english_name']]) \
                        .execute()
                    
                    if aresp.data:
                        asset_id = aresp.data[0]['id']
                        # Check if quest-asset link already exists
                        existing_link = self.supabase.table('quest_asset_link') \
                            .select('quest_id') \
                            .eq('quest_id', quest_id) \
                            .eq('asset_id', asset_id) \
                            .execute()
                        
                        if not existing_link.data:
                            # Create quest-asset link only if it doesn't exist
                            self.supabase.table('quest_asset_link') \
                                .insert({
                                    'quest_id': quest_id,
                                    'asset_id': asset_id
                                }) \
                                .execute()
                            
                            # Record the creation
                            if self.session_recorder:
                                self.session_recorder.add_record('quest_asset_links', f"{quest_id}_{asset_id}", {
                                    'quest_id': quest_id,
                                    'asset_id': asset_id
                                })
                
                # Collect unique books and chapters from all verses
                quest_books = set()
                quest_chapters = set()
                
                # Get book abbreviation config
                book_abbr_config = self.config.get('book_abbreviations', {})
                
                for verse_ref, _ in all_verses:
                    book_code, chapter, verse = verse_ref.split('_', 2)
                    
                    # Get formatted book name
                    if book_abbr_config.get('use_localized', False):
                        formatted_book = get_localized_book_name(
                            book_code, 
                            proj['source_language_english_name'], 
                            self.book_names_data
                        )
                    else:
                        formatted_book = book_code.title()
                    
                    quest_books.add(formatted_book)
                    quest_chapters.add((formatted_book, chapter))
                
                # Get tag labels from config
                tag_labels = self.config.get('tag_labels', {
                    'book': 'book',
                    'chapter': 'chapter',
                    'verse': 'verse'
                })
                
                # Add book and chapter tags for quest
                quest_tags = []
                
                # Add book tags
                for book in quest_books:
                    quest_tags.append(f"{tag_labels['book']}:{book}")
                
                # Add chapter tags (only if quest covers a single book)
                if len(quest_books) == 1:
                    for book, chapter in quest_chapters:
                        quest_tags.append(f"{tag_labels['chapter']}:{chapter}")
                
                # Add additional tags from JSON
                quest_tags.extend(quest.get('additional_tags', []))
                
                print(f"Quest tags to add: {quest_tags}")
                
                # Create quest-tag links
                for tag_name in quest_tags:
                    tag_id = get_or_create_tag(self.supabase, tag_cache, tag_name)
                    
                    # Check if link exists
                    existing = self.supabase.table('quest_tag_link') \
                        .select('quest_id') \
                        .eq('quest_id', quest_id) \
                        .eq('tag_id', tag_id) \
                        .execute()
                    
                    if not existing.data:
                        self.supabase.table('quest_tag_link') \
                            .insert({'quest_id': quest_id, 'tag_id': tag_id}) \
                            .execute()
                        print(f"  Added quest tag: {tag_name}")
                        
                        # Record the creation
                        if self.session_recorder:
                            self.session_recorder.add_record('quest_tag_links', f"{quest_id}_{tag_id}", {
                                'quest_id': quest_id,
                                'tag_id': tag_id
                            })
                    else:
                        print(f"  Quest tag already exists: {tag_name}")


def delete_session(record_file: str):
    """Delete all records created in a session based on the record file"""
    print(f"\nDeleting session from record file: {record_file}")
    
    # Handle both direct file path and just filename
    if not os.path.exists(record_file):
        # Try looking in session_records directory
        alt_path = os.path.join('session_records', record_file)
        if os.path.exists(alt_path):
            record_file = alt_path
        else:
            print(f"Error: Record file '{record_file}' not found!")
            return
    
    # Load the record file
    with open(record_file, 'r', encoding='utf-8') as f:
        records = json.load(f)
    
    # Initialize Supabase client
    load_dotenv()
    sb = get_supabase_client()
    
    # Delete in reverse order to handle dependencies
    deletion_order = [
        ('quest_tag_links', 'quest_tag_link'),
        ('asset_tag_links', 'asset_tag_link'),
        ('quest_asset_links', 'quest_asset_link'),
        ('asset_content_links', 'asset_content_link'),
        ('assets', 'asset'),
        ('quests', 'quest'),
        ('projects', 'project'),
        ('tags', 'tag'),
        ('languages', 'language')
    ]
    
    for record_key, table_name in deletion_order:
        if record_key in records and records[record_key]:
            print(f"\nDeleting {len(records[record_key])} {record_key}...")
            for record in records[record_key]:
                try:
                    if '_' in record['id'] and record_key.endswith('_links'):
                        # For composite keys (link tables)
                        parts = record['id'].split('_')
                        if record_key == 'quest_tag_links':
                            sb.table(table_name).delete() \
                                .eq('quest_id', parts[0]) \
                                .eq('tag_id', parts[1]) \
                                .execute()
                        elif record_key == 'asset_tag_links':
                            sb.table(table_name).delete() \
                                .eq('asset_id', parts[0]) \
                                .eq('tag_id', parts[1]) \
                                .execute()
                        elif record_key == 'quest_asset_links':
                            sb.table(table_name).delete() \
                                .eq('quest_id', parts[0]) \
                                .eq('asset_id', parts[1]) \
                                .execute()
                    else:
                        # For regular tables with single ID
                        sb.table(table_name).delete() \
                            .eq('id', record['id']) \
                            .execute()
                    print(f"  Deleted {record_key[:-1]}: {record['id']}")
                except Exception as e:
                    print(f"  Error deleting {record_key[:-1]} {record['id']}: {e}")
    
    # Delete audio files from storage
    if 'audio_files' in records and records['audio_files']:
        print(f"\nDeleting {len(records['audio_files'])} audio files...")
        for audio in records['audio_files']:
            try:
                sb.storage.from_(audio['bucket']).remove([audio['path']])
                print(f"  Deleted audio file: {audio['path']}")
            except Exception as e:
                print(f"  Error deleting audio file {audio['path']}: {e}")
    
    print("\nDeletion complete!")


def main():
    # Check for delete mode
    if len(sys.argv) > 1 and sys.argv[1] == '--delete':
        if len(sys.argv) < 3:
            print("Error: Please provide the record file to delete")
            print("Usage: python master_scripture_processor.py --delete session_record_YYYYMMDD_HHMMSS.json")
            return
        delete_session(sys.argv[2])
        return
    
    # Normal mode
    CONFIG_FILE = "config_pt-BR_bible.json"  # Change this to your desired config file path
    
    # Check if config file exists
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found!")
        print("Please create a configuration file or update the CONFIG_FILE path.")
        return
    
    # Create session recorder
    session_recorder = SessionRecorder()
    
    # Run processor with session recorder
    processor = MasterScriptureProcessor(CONFIG_FILE, session_recorder)
    processor.run()
    
    # Save session record
    session_recorder.save()


if __name__ == "__main__":
    main() 