#!/usr/bin/env python3
"""
Unified Content Processor
Main processor that handles both Bible verses and line-based content
"""

import os
import json
import csv
import uuid
import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

from unified_content_handlers import ContentHandler, BibleContentHandler, LinesContentHandler
from unified_content_handlers.supabase_handler import SupabaseHandler
from unified_content_handlers.audio_handler import AudioHandler

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
            "project_language_links": [],
            "audio_files": [],
            "local_audio_files": [],
            "audio_failures": []
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


class UnifiedContentProcessor:
    """Main processor for all content types"""
    
    def __init__(self, config_file: str, resume_file: Optional[str] = None):
        """Initialize with configuration from JSON file"""
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Initialize session recorder
        self.session_recorder = SessionRecorder()
        
        # Initialize handlers
        self.supabase = SupabaseHandler()
        
        # Initialize content handler based on type
        content_type = self.config.get('content_type', 'bible')
        self.content_type = content_type
        if content_type == 'bible':
            self.content_handler = BibleContentHandler(self.config)
        elif content_type == 'lines':
            self.content_handler = LinesContentHandler(self.config)
        else:
            raise ValueError(f"Unsupported content type: {content_type}")
        
        # Initialize audio handler if needed
        audio_config = self.config.get('audio_generation', {})
        if audio_config.get('save_local', False) or audio_config.get('save_to_database', False):
            self.audio_handler = AudioHandler(self.config)
        else:
            self.audio_handler = None
        
        # Resume support
        self.resume_file = resume_file
        self.resume_data = None
        if resume_file:
            try:
                with open(resume_file, 'r', encoding='utf-8') as rf:
                    self.resume_data = json.load(rf)
                logger.info(f"Resume mode enabled from {resume_file}")
            except Exception as e:
                logger.warning(f"Failed to load resume file {resume_file}: {e}")
        
        logger.info(f"Initialized {content_type} content processor")
    
    async def process_quest_content(self, quest: Dict[str, Any], project_info: Dict[str, Any],
                                   lang_map: Dict[str, str], tag_cache: Dict[str, str],
                                   project_id: str, quest_id: str) -> None:
        """Process content for a single quest"""
        
        # Get content items using the appropriate handler
        content_items = self.content_handler.get_content_items(quest)
        # Resume support: optionally skip completed refs by checking DB if resume is enabled
        processed_refs: set = set()
        if self.resume_data:
            # Build a set of asset ids already linked for this quest and language
            # This is a best-effort: it will skip items with existing per-language content links
            pass
        
        if not content_items:
            logger.warning(f"No content items found for quest: {quest['name']}")
            return
        
        logger.info(f"Processing {len(content_items)} items for quest: {quest['name']}")
        
        # Get configuration
        audio_config = self.config.get('audio_generation', {})
        save_local = audio_config.get('save_local', False)
        save_to_database = audio_config.get('save_to_database', False)
        generate_audio = save_local or save_to_database
        
        # Determine the active source language for this quest
        # New schema allows multiple source languages; config may specify mapping for CSV per language
        source_lang_name = project_info.get('source_language_english_name')
        if isinstance(source_lang_name, list):
            # If multiple, fall back to the first unless overridden by quest-level 'source_language_english_name'
            source_lang_name = quest.get('source_language_english_name', source_lang_name[0])
        else:
            # Quest-level override if present
            source_lang_name = quest.get('source_language_english_name', source_lang_name)
        source_lang_id = lang_map[source_lang_name]
        
        # Prepare batch for processing
        audio_batch = []
        item_metadata = {}
        
        for reference, text in content_items:
            if reference in processed_refs:
                continue
            # Format asset name
            asset_name = self.content_handler.format_asset_name(reference, source_lang_name)
            
            # Create or get project-scoped asset (never reuse names from other projects)
            existing_asset = self.supabase.execute_with_retry(
                self.supabase.client.table('asset').select('id').eq('name', asset_name)
            )
            asset_id = self.supabase.get_or_create_project_scoped_asset(
                asset_name, project_id, legacy_source_language_id=source_lang_id
            )
            
            # Only record if it's a new asset
            # Record as new if the returned id differs from any existing-by-name id
            if not existing_asset.data or existing_asset.data[0]['id'] != asset_id:
                self.session_recorder.add_record('assets', asset_id, {
                    'name': asset_name,
                    'source_language_id': source_lang_id
                })
            
            # Idempotency/resume: only skip if content exists AND already has audio
            existing_lang_content = self.supabase.execute_with_retry(
                self.supabase.client.table('asset_content_link')
                    .select('id,audio_id')
                    .eq('asset_id', asset_id)
                    .eq('source_language_id', source_lang_id)
            )
            if existing_lang_content.data and existing_lang_content.data[0].get('audio_id'):
                # Always ensure quest-asset link for this project to the project-scoped asset we selected/created
                self.supabase.upsert_quest_asset_link(quest_id, asset_id)
                continue
            
            # Store metadata
            item_metadata[reference] = {
                'asset_id': asset_id,
                'asset_name': asset_name,
                'text': text,
                'reference': reference
            }
            
            # Prepare audio generation if needed
            if generate_audio and self.audio_handler:
                # Get audio configuration
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
                elif provider == 'google':
                    # Prefer explicit voice_name; fallback to language_code for stable naming
                    voice = audio_config.get('google', {}).get('voice_name') or audio_config.get('google', {}).get('language_code', 'default')
                else:
                    voice = 'default'
                
                # Get language code
                lang_code = project_info.get('source_language_iso_code', 
                                           project_info['source_language_english_name'])
                
                # Check for existing audio
                audio_id = None
                reuse_existing = audio_config.get('reuse_existing_audio', True)
                
                if save_to_database and reuse_existing:
                    audio_id = self.supabase.find_existing_audio(
                        content_folder, reference, lang_code, voice, source_language_id=source_lang_id
                    )
                    if audio_id:
                        logger.info(f"Reusing existing audio for {reference}")
                        item_metadata[reference]['audio_id'] = audio_id
                
                # Add to batch if no existing audio
                if not audio_id:
                    file_uuid = str(uuid.uuid4())
                    filename = f"{reference}_{lang_code}_{voice}_{file_uuid}.m4a"
                    
                    # Determine output path
                    if save_local:
                        local_dir = os.path.join("generated_audio", project_name)
                        os.makedirs(local_dir, exist_ok=True)
                        local_path = os.path.join(local_dir, filename)
                    else:
                        local_path = f"temp_{asset_id}.m4a"
                    
                    audio_batch.append((text, local_path))
                    item_metadata[reference]['pending_audio'] = {
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
                # Find the corresponding item
                for reference, metadata in item_metadata.items():
                    if 'pending_audio' in metadata and metadata['pending_audio']['local_path'] == output_path:
                        if success:
                            pending = metadata['pending_audio']
                            
                            # Record local file if saved
                            if pending['save_local']:
                                self.session_recorder.add_record('local_audio_files', output_path, {
                                    'path': output_path,
                                    'reference': reference
                                })
                            
                            # Upload to database if configured
                            if pending['save_to_database']:
                                storage_config = self.config.get('storage', {})
                                bucket_name = storage_config.get('bucket_name', 'assets')
                                content_folder = storage_config.get('content_folder', 'content')
                                
                                storage_path = f"{content_folder}/{pending['filename']}"
                                audio_url = self.supabase.upload_audio_to_storage(
                                    output_path, storage_path, bucket_name
                                )
                                if audio_url:
                                    metadata['audio_id'] = storage_path
                                    logger.info(f"Uploaded audio for {reference}")
                                    
                                    # Record audio file creation
                                    self.session_recorder.add_record('audio_files', storage_path, {
                                        'bucket': bucket_name,
                                        'path': storage_path
                                    })
                            
                            # Clean up temp file if not saving locally
                            if not pending['save_local'] and os.path.exists(output_path):
                                os.remove(output_path)
                        else:
                            logger.error(f"Failed to generate audio for {reference}")
                        break
            # Log failures but do not abort; record them in session file
            failed = [p for p, ok in audio_results if not ok]
            if failed:
                for output_path in failed:
                    # Map output_path back to reference for better reporting
                    ref_for_path = None
                    for reference, metadata in item_metadata.items():
                        if 'pending_audio' in metadata and metadata['pending_audio']['local_path'] == output_path:
                            ref_for_path = reference
                            break
                    logger.error(f"Audio generation failed for {ref_for_path or output_path}")
                    # Record failure in session file
                    self.session_recorder.add_record('audio_failures', ref_for_path or output_path, {
                        'output_path': output_path,
                        'reference': ref_for_path,
                    })
        
        # Process all database updates
        for reference, metadata in item_metadata.items():
            asset_id = metadata['asset_id']
            text = metadata['text']
            audio_id = metadata.get('audio_id')
            
            # Check if content link exists for this language
            existing_content_link = self.supabase.execute_with_retry(
                self.supabase.client.table('asset_content_link')
                    .select('id')
                    .eq('asset_id', asset_id)
                    .eq('source_language_id', source_lang_id)
            )
            
            # Update content link for this language
            self.supabase.upsert_asset_content_link(asset_id, text, source_language_id=source_lang_id, audio_id=audio_id)
            
            # Only record if it's a new content link
            if not existing_content_link.data:
                self.session_recorder.add_record('asset_content_links', f"{asset_id}_content_{source_lang_id}", {
                    'asset_id': asset_id,
                    'source_language_id': source_lang_id,
                    'has_audio': bool(audio_id)
                })
            
            # Check if quest-asset link exists
            existing_quest_asset_link = self.supabase.execute_with_retry(
                self.supabase.client.table('quest_asset_link')
                    .select('quest_id')
                    .eq('quest_id', quest_id)
                    .eq('asset_id', asset_id)
            )
            
            # Create quest-asset link
            self.supabase.upsert_quest_asset_link(quest_id, asset_id)
            
            # Only record if it's a new link
            if not existing_quest_asset_link.data:
                self.session_recorder.add_record('quest_asset_links', f"{quest_id}_{asset_id}", {
                    'quest_id': quest_id,
                    'asset_id': asset_id
                })
            
            # Add tags
            tags = self.content_handler.get_tags(reference)
            for tag_name in tags:
                # Check if tag already exists before creating
                was_new_tag = tag_name not in tag_cache
                tag_id = self.supabase.get_or_create_tag(tag_name, tag_cache)
                
                # Record tag creation if new
                if was_new_tag:
                    self.session_recorder.add_record('tags', tag_id, {'name': tag_name})
                
                # Check if asset-tag link exists
                existing_asset_tag_link = self.supabase.execute_with_retry(
                    self.supabase.client.table('asset_tag_link')
                        .select('asset_id')
                        .eq('asset_id', asset_id)
                        .eq('tag_id', tag_id)
                )
                
                self.supabase.upsert_asset_tag_link(asset_id, tag_id)
                
                # Only record if it's a new link
                if not existing_asset_tag_link.data:
                    self.session_recorder.add_record('asset_tag_links', f"{asset_id}_{tag_id}", {
                        'asset_id': asset_id,
                        'tag_id': tag_id
                    })
        
        # Add quest-level tags
        for tag_name in quest.get('additional_tags', []):
            # Check if tag already exists before creating
            was_new_tag = tag_name not in tag_cache
            tag_id = self.supabase.get_or_create_tag(tag_name, tag_cache)
            
            # Record tag creation if new
            if was_new_tag:
                self.session_recorder.add_record('tags', tag_id, {'name': tag_name})
            
            # Check if quest-tag link exists
            existing_quest_tag_link = self.supabase.execute_with_retry(
                self.supabase.client.table('quest_tag_link')
                    .select('quest_id')
                    .eq('quest_id', quest_id)
                    .eq('tag_id', tag_id)
            )
            
            self.supabase.upsert_quest_tag_link(quest_id, tag_id)
            
            # Only record if it's a new link
            if not existing_quest_tag_link.data:
                self.session_recorder.add_record('quest_tag_links', f"{quest_id}_{tag_id}", {
                    'quest_id': quest_id,
                    'tag_id': tag_id
                })
    
    def process_quest(self, quest: Dict[str, Any], project_info: Dict[str, Any],
                     lang_map: Dict[str, str], tag_cache: Dict[str, str],
                     project_id: str, quest_id: str) -> None:
        """Sync wrapper for process_quest_content"""
        asyncio.run(self.process_quest_content(
            quest, project_info, lang_map, tag_cache, project_id, quest_id
        ))
    
    def run(self):
        """Main execution method"""
        start_time = time.time()
        
        # Get project files
        project_files = []
        if 'project_file' in self.config:
            project_files = [self.config['project_file']]
        elif 'project_files' in self.config:
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
        
        # Save session record
        self.session_recorder.save()
        
        # Attempt to rebuild closures on the server for all processed projects
        # This relies on RPC functions being present; otherwise it's a no-op.
        try:
            for project_file in project_files:
                with open(project_file, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                for proj in project_data['projects']:
                    existing_project = self.supabase.client.table('project') \
                        .select('id') \
                        .eq('name', proj['name']) \
                        .execute()
                    if existing_project.data:
                        self.supabase.rebuild_project_closure(existing_project.data[0]['id'])
        except Exception as e:
            logger.warning(f"Closure rebuild RPC skipped/failed: {e}")
        
        # Display execution time
        end_time = time.time()
        total_time = end_time - start_time
        
        if total_time < 60:
            time_str = f"{total_time:.2f} seconds"
        elif total_time < 3600:
            minutes = total_time / 60
            time_str = f"{minutes:.2f} minutes"
        else:
            hours = total_time / 3600
            time_str = f"{hours:.2f} hours"
        
        print(f"\nAll projects processed!")
        print(f"Total execution time: {time_str}")
    
    def _process_project_data(self, project_data: Dict[str, Any]):
        """Process a single project data object"""
        
        # Process languages
        lang_map = {}
        
        # Process languages from project data if provided
        if 'languages' in project_data:
            for lang in project_data['languages']:
                # Check if language already exists
                existing_lang_id = self.supabase.get_language_by_name(lang['english_name'])
                
                lang_id = self.supabase.upsert_language(lang)
                lang_map[lang['english_name']] = lang_id
                
                # Only record if it's a new language
                if not existing_lang_id:
                    self.session_recorder.add_record('languages', lang_id, {
                        'english_name': lang['english_name'],
                        'iso639_3': lang.get('iso639_3')
                    })
        
        # Fetch any additional languages from DB (supports list of sources)
        for proj in project_data['projects']:
            source_names = proj.get('source_language_english_name')
            if isinstance(source_names, list):
                candidates = source_names
            else:
                candidates = [source_names]
            candidates.append(proj.get('target_language_english_name'))
            for lang_name in [n for n in candidates if n]:
                if lang_name not in lang_map:
                    lang_id = self.supabase.get_language_by_name(lang_name)
                    if lang_id:
                        lang_map[lang_name] = lang_id
                        print(f"Using existing language from database: {lang_name}")
                    else:
                        raise RuntimeError(
                            f"Language '{lang_name}' not found in database. "
                            f"Either add it to the 'languages' section in your project file, "
                            f"or ensure it exists in the database."
                        )
        
        # Process projects and quests
        tag_cache = {}
        for proj in project_data['projects']:
            # Check if project already exists by name only
            existing_project = self.supabase.execute_with_retry(
                self.supabase.client.table('project').select('id').eq('name', proj['name'])
            )
            
            project_id = self.supabase.upsert_project(proj, lang_map)
            
            if existing_project.data:
                print(f"\nUsing existing project: {proj['name']} (ID: {project_id})")
            else:
                print(f"\nCreating new project: {proj['name']} (ID: {project_id})")
                # Only record if it's a new project
                self.session_recorder.add_record('projects', project_id, {
                    'name': proj['name']
                })

            # Ensure project_language_link entries (multiple sources + single target)
            source_names = proj.get('source_language_english_name')
            if isinstance(source_names, list):
                source_list = source_names
            else:
                source_list = [source_names]
            for src_name in source_list:
                self.supabase.upsert_project_language_link(project_id, lang_map[src_name], 'source')
                self.session_recorder.add_record('project_language_links', f"{project_id}_{lang_map[src_name]}_source", {
                    'project_id': project_id,
                    'language_id': lang_map[src_name],
                    'language_type': 'source'
                })
            tgt_name = proj.get('target_language_english_name')
            if tgt_name:
                self.supabase.upsert_project_language_link(project_id, lang_map[tgt_name], 'target')
                self.session_recorder.add_record('project_language_links', f"{project_id}_{lang_map[tgt_name]}_target", {
                    'project_id': project_id,
                    'language_id': lang_map[tgt_name],
                    'language_type': 'target'
                })
            
            # Handle optional CSV datasets for this project
            csv_datasets = proj.get('csv_datasets') or project_data.get('csv_datasets')
            if csv_datasets:
                self._process_csv_datasets(
                    csv_datasets=csv_datasets,
                    project_info=proj,
                    lang_map=lang_map,
                    tag_cache=tag_cache,
                    project_id=project_id
                )

            for quest in proj.get('quests', []):
                # Check if quest already exists
                existing_quest = self.supabase.execute_with_retry(
                    self.supabase.client.table('quest')
                        .select('id')
                        .eq('name', quest['name'])
                        .eq('project_id', project_id)
                )
                
                quest_id = self.supabase.upsert_quest(quest, project_id)
                
                if existing_quest.data:
                    print(f"  Using existing quest: {quest['name']} (ID: {quest_id})")
                else:
                    print(f"  Creating new quest: {quest['name']} (ID: {quest_id})")
                    # Only record if it's a new quest
                    self.session_recorder.add_record('quests', quest_id, {
                        'name': quest['name'],
                        'project_id': project_id
                    })
                
                # Process content for this quest
                self.process_quest(quest, proj, lang_map, tag_cache, project_id, quest_id)
                # Attempt to rebuild this quest's closure after content
                try:
                    self.supabase.rebuild_quest_closure(quest_id)
                except Exception as e:
                    logger.warning(f"Quest closure rebuild RPC failed for {quest_id}: {e}")

    def _process_csv_datasets(self, csv_datasets: List[Dict[str, Any]], project_info: Dict[str, Any],
                               lang_map: Dict[str, str], tag_cache: Dict[str, str], project_id: str) -> None:
        """Process multiple CSV datasets mapped to specific source languages"""
        audio_config = self.config.get('audio_generation', {})
        save_local = audio_config.get('save_local', False)
        save_to_database = audio_config.get('save_to_database', False)
        generate_audio = save_local or save_to_database

        # Provider-specific voice
        provider = audio_config.get('provider', 'openai')
        if provider == 'openai':
            default_voice = audio_config.get('openai', {}).get('voice', 'onyx')
        elif provider == 'elevenlabs':
            default_voice = audio_config.get('elevenlabs', {}).get('voice_id', 'default')
        elif provider == 'google':
            default_voice = audio_config.get('google', {}).get('voice_name') or audio_config.get('google', {}).get('language_code', 'default')
        else:
            default_voice = 'default'

        storage_config = self.config.get('storage', {})
        bucket_name = storage_config.get('bucket_name', 'assets')
        content_folder = storage_config.get('content_folder', 'content')

        project_name = project_info.get('name', 'default').replace(' ', '_')

        # Build lookup for ISO codes if provided in languages section
        english_to_iso = {}
        for lang in project_info.get('languages', []) + project_info.get('additional_languages', []):
            if isinstance(lang, dict) and lang.get('english_name'):
                if 'iso639_3' in lang:
                    english_to_iso[lang['english_name']] = lang['iso639_3']

        for dataset in csv_datasets:
            path = dataset['path']
            src_lang_name = dataset['language_english_name']
            ref_col = dataset.get('reference_column', 'reference')
            text_col = dataset.get('text_column', 'text')
            voice = dataset.get('voice') or default_voice
            quest_name = dataset.get('quest_name') or f"CSV Import - {src_lang_name}"
            lang_code = dataset.get('language_code') or english_to_iso.get(src_lang_name) or src_lang_name

            # Ensure language exists and is linked to project as source
            if src_lang_name not in lang_map:
                lang_id = self.supabase.get_language_by_name(src_lang_name)
                if not lang_id:
                    raise RuntimeError(f"Language '{src_lang_name}' not found in DB for dataset {path}")
                lang_map[src_lang_name] = lang_id
            src_lang_id = lang_map[src_lang_name]
            self.supabase.upsert_project_language_link(project_id, src_lang_id, 'source')

            # Upsert quest for this dataset
            quest = {'name': quest_name, 'description': dataset.get('description', '')}
            quest_id = self.supabase.upsert_quest(quest, project_id)

            # Read CSV
            with open(path, 'r', encoding=dataset.get('encoding', 'utf-8')) as f:
                reader = csv.DictReader(f)
                audio_batch = []
                item_metadata: Dict[str, Dict[str, Any]] = {}

                for row in reader:
                    reference = row[ref_col].strip()
                    text = row[text_col]

                    # Format asset name using selected content handler
                    asset_name = self.content_handler.format_asset_name(reference, src_lang_name)

                    # Upsert asset (language-agnostic)
                    existing_asset = self.supabase.client.table('asset').select('id').eq('name', asset_name).execute()
                    asset_id = self.supabase.get_or_create_project_scoped_asset(asset_name, project_id)

                    if not existing_asset.data or existing_asset.data[0]['id'] != asset_id:
                        self.session_recorder.add_record('assets', asset_id, {'name': asset_name})

                    # Prepare audio if needed
                    audio_id = None
                    if generate_audio and self.audio_handler:
                        reuse_existing = audio_config.get('reuse_existing_audio', True)
                        if save_to_database and reuse_existing:
                            audio_id = self.supabase.find_existing_audio(content_folder, reference, lang_code, voice, source_language_id=src_lang_id)
                            if audio_id:
                                item_metadata[reference] = {'asset_id': asset_id, 'text': text, 'audio_id': audio_id}

                        if not audio_id:
                            file_uuid = str(uuid.uuid4())
                            filename = f"{reference}_{lang_code}_{voice}_{file_uuid}.m4a"
                            if save_local:
                                local_dir = os.path.join('generated_audio', project_name)
                                os.makedirs(local_dir, exist_ok=True)
                                local_path = os.path.join(local_dir, filename)
                            else:
                                local_path = f"temp_{asset_id}.m4a"
                            audio_batch.append((text, local_path))
                            item_metadata.setdefault(reference, {'asset_id': asset_id, 'text': text})
                            item_metadata[reference]['pending_audio'] = {
                                'local_path': local_path,
                                'filename': filename,
                                'save_local': save_local,
                                'save_to_database': save_to_database
                            }
                    else:
                        item_metadata[reference] = {'asset_id': asset_id, 'text': text}

                # Generate audio in parallel
                if audio_batch and self.audio_handler:
                    logger.info(f"Generating {len(audio_batch)} audio files concurrently for {quest_name}...")
                    audio_results = asyncio.run(self.audio_handler.generate_multiple_audio(audio_batch))
                    for output_path, success in audio_results:
                        for reference, metadata in item_metadata.items():
                            if 'pending_audio' in metadata and metadata['pending_audio']['local_path'] == output_path:
                                if success:
                                    pending = metadata['pending_audio']
                                    if pending['save_local']:
                                        self.session_recorder.add_record('local_audio_files', output_path, {'path': output_path, 'reference': reference})
                                    if pending['save_to_database']:
                                        storage_path = f"{content_folder}/{pending['filename']}"
                                        audio_url = self.supabase.upload_audio_to_storage(output_path, storage_path, bucket_name)
                                        if audio_url:
                                            metadata['audio_id'] = storage_path
                                            self.session_recorder.add_record('audio_files', storage_path, {'bucket': bucket_name, 'path': storage_path})
                                    if not pending['save_local'] and os.path.exists(output_path):
                                        os.remove(output_path)
                                else:
                                    logger.error(f"Failed to generate audio for {reference}")
                                    # Record failure in session
                                    self.session_recorder.add_record('audio_failures', reference, {
                                        'output_path': output_path,
                                        'reference': reference,
                                    })
                                break

                # Upsert content links, tags, and quest-asset links
                for reference, metadata in item_metadata.items():
                    asset_id = metadata['asset_id']
                    text = metadata['text']
                    audio_id = metadata.get('audio_id')

                    existing_content_link = self.supabase.client.table('asset_content_link') \
                        .select('id') \
                        .eq('asset_id', asset_id) \
                        .eq('source_language_id', src_lang_id) \
                        .execute()
                    self.supabase.upsert_asset_content_link(asset_id, text, source_language_id=src_lang_id, audio_id=audio_id)
                    if not existing_content_link.data:
                        self.session_recorder.add_record('asset_content_links', f"{asset_id}_content_{src_lang_id}", {
                            'asset_id': asset_id,
                            'source_language_id': src_lang_id,
                            'has_audio': bool(audio_id)
                        })

                    existing_quest_asset_link = self.supabase.client.table('quest_asset_link') \
                        .select('quest_id') \
                        .eq('quest_id', quest_id) \
                        .eq('asset_id', asset_id) \
                        .execute()
                    self.supabase.upsert_quest_asset_link(quest_id, asset_id)
                    if not existing_quest_asset_link.data:
                        self.session_recorder.add_record('quest_asset_links', f"{quest_id}_{asset_id}", {'quest_id': quest_id, 'asset_id': asset_id})

                    # Tags
                    tags = self.content_handler.get_tags(reference)
                    for tag_name in tags:
                        was_new_tag = tag_name not in tag_cache
                        tag_id = self.supabase.get_or_create_tag(tag_name, tag_cache)
                        if was_new_tag:
                            self.session_recorder.add_record('tags', tag_id, {'name': tag_name})
                        existing_asset_tag_link = self.supabase.client.table('asset_tag_link') \
                            .select('asset_id') \
                            .eq('asset_id', asset_id) \
                            .eq('tag_id', tag_id) \
                            .execute()
                        self.supabase.upsert_asset_tag_link(asset_id, tag_id)
                        if not existing_asset_tag_link.data:
                            self.session_recorder.add_record('asset_tag_links', f"{asset_id}_{tag_id}", {'asset_id': asset_id, 'tag_id': tag_id})


def delete_session(record_file: str):
    """Delete all records from a session using the session record file"""
    from unified_content_handlers.supabase_handler import SupabaseHandler
    
    print(f"\nDeleting session from: {record_file}")
    
    with open(record_file, 'r') as f:
        session_data = json.load(f)
    
    sb = SupabaseHandler()
    
    # Delete in reverse order of creation to handle dependencies
    
    # 1. Delete audio files from storage
    for audio in session_data.get('audio_files', []):
        try:
            sb.client.storage.from_(audio['bucket']).remove([audio['path']])
            print(f"Deleted audio file: {audio['path']}")
        except Exception as e:
            print(f"Error deleting audio {audio['path']}: {e}")
    
    # 2. Delete local audio files
    for local_audio in session_data.get('local_audio_files', []):
        try:
            if os.path.exists(local_audio['path']):
                os.remove(local_audio['path'])
                print(f"Deleted local audio file: {local_audio['path']}")
        except Exception as e:
            print(f"Error deleting local file {local_audio['path']}: {e}")
    
    # 3. Delete quest-tag links
    for link in session_data.get('quest_tag_links', []):
        try:
            sb.client.table('quest_tag_link') \
                .delete() \
                .eq('quest_id', link['quest_id']) \
                .eq('tag_id', link['tag_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting quest-tag link: {e}")
    
    # 4. Delete asset-tag links
    for link in session_data.get('asset_tag_links', []):
        try:
            sb.client.table('asset_tag_link') \
                .delete() \
                .eq('asset_id', link['asset_id']) \
                .eq('tag_id', link['tag_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting asset-tag link: {e}")
    
    # 5. Delete quest-asset links
    for link in session_data.get('quest_asset_links', []):
        try:
            sb.client.table('quest_asset_link') \
                .delete() \
                .eq('quest_id', link['quest_id']) \
                .eq('asset_id', link['asset_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting quest-asset link: {e}")
    
    # 6. Delete asset content links
    for link in session_data.get('asset_content_links', []):
        try:
            sb.client.table('asset_content_link') \
                .delete() \
                .eq('asset_id', link['asset_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting asset content link: {e}")
    
    # 7. Delete assets
    for asset in session_data.get('assets', []):
        try:
            sb.client.table('asset') \
                .delete() \
                .eq('id', asset['id']) \
                .execute()
            print(f"Deleted asset: {asset['name']}")
        except Exception as e:
            print(f"Error deleting asset {asset['id']}: {e}")
    
    # 8. Delete quests
    for quest in session_data.get('quests', []):
        try:
            sb.client.table('quest') \
                .delete() \
                .eq('id', quest['id']) \
                .execute()
            print(f"Deleted quest: {quest['name']}")
        except Exception as e:
            print(f"Error deleting quest {quest['id']}: {e}")
    
    # 9. Delete projects
    for project in session_data.get('projects', []):
        try:
            sb.client.table('project') \
                .delete() \
                .eq('id', project['id']) \
                .execute()
            print(f"Deleted project: {project['name']}")
        except Exception as e:
            print(f"Error deleting project {project['id']}: {e}")
    
    # Note: We don't delete languages or tags as they might be used elsewhere
    
    print("\nSession deletion complete!")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process content and upload to Supabase")
    parser.add_argument('config_file', nargs='?', help='Configuration JSON file')
    parser.add_argument('--delete', metavar='SESSION_FILE', 
                       help='Delete a session using its record file')
    args = parser.parse_args()
    
    if args.delete:
        # Delete mode
        delete_session(args.delete)
    elif args.config_file:
        # Normal processing mode
        processor = UnifiedContentProcessor(args.config_file)
        processor.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 