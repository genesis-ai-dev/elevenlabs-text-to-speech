#!/usr/bin/env python3
"""
Master Scripture Processor
Coordinates scripture reference extraction, Supabase uploads, and audio generation
"""

import os
import json
import uuid
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client
from elevenlabs import ElevenLabs
from pydub import AudioSegment
import io

from ScriptureReference import ScriptureReference
from supabase_upload_quests import (
    get_supabase_client, 
    load_book_names,
    get_localized_book_name,
    upsert_language,
    upsert_project,
    get_or_create_tag
)


class SessionRecorder:
    """Records all database operations for potential rollback"""
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"session_record_{self.timestamp}.json"
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
            "audio_files": []
        }
    
    def add_record(self, table: str, record_id: str, additional_info: dict = None):
        """Add a record to the session"""
        record = {"id": record_id}
        if additional_info:
            record.update(additional_info)
        
        if table in self.records:
            self.records[table].append(record)
    
    def save(self):
        """Save the session record to file"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2)
        print(f"\nSession record saved to: {self.filename}")
        return self.filename


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
        
        # Initialize ElevenLabs if audio generation is enabled
        if self.config.get('audio_generation', {}).get('enabled', False):
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not found in environment")
            self.elevenlabs = ElevenLabs(api_key=api_key)
        
        # Load book names if localization is enabled
        self.book_names_data = {}
        if self.config.get('book_abbreviations', {}).get('use_localized', False):
            self.book_names_data = load_book_names()
    
    def generate_audio_v3(self, text: str, output_path: str, voice_id: str) -> bool:
        """Generate audio using ElevenLabs v3 API"""
        try:
            # Use the v3 API endpoint
            audio_generator = self.elevenlabs.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            
            # Collect audio bytes from generator
            audio_bytes = b"".join(audio_generator)
            
            # Convert MP3 to M4A
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'
            
            # Export as M4A
            audio_segment.export(output_path, format="mp4", codec="aac")
            print(f"Audio saved successfully to {output_path}")
            return True
            
        except Exception as e:
            print(f"Error generating audio: {str(e)}")
            return False
    
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
            print(f"Error uploading audio to storage: {str(e)}")
            return None
    
    def process_verses(self, verses: List[Tuple[str, str]], project_info: Dict, 
                      lang_map: Dict, tag_cache: Dict, project_id: str, quest_id: str) -> None:
        """Process verses for a quest, creating assets and optionally generating audio"""
        
        audio_config = self.config.get('audio_generation', {})
        generate_audio = audio_config.get('enabled', False)
        voice_id = audio_config.get('voice_id')
        
        book_abbr_config = self.config.get('book_abbreviations', {})
        use_localized = book_abbr_config.get('use_localized', False)
        abbr_language = book_abbr_config.get('language', 'en')
        
        source_lang_id = lang_map[project_info['source_language_english_name']]
        
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
            # First check if asset is already linked to this quest
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
            
            # Handle audio generation/reuse
            audio_id = None
            if generate_audio and voice_id:
                # Get storage configuration
                storage_config = self.config.get('storage', {})
                bucket_name = storage_config.get('bucket_name', 'assets')
                content_folder = storage_config.get('content_folder', 'content')
                
                # Check if audio already exists for this verse reference
                # Look for any existing audio file with this verse reference
                existing_audio = self.supabase.table('asset_content_link') \
                    .select('audio_id') \
                    .like('audio_id', f'{content_folder}/{verse_ref}_%') \
                    .limit(1) \
                    .execute()
                
                if existing_audio.data and existing_audio.data[0]['audio_id']:
                    # Reuse existing audio file
                    audio_id = existing_audio.data[0]['audio_id']
                    print(f"Reusing existing audio for {verse_ref}: {audio_id}")
                else:
                    # Generate new audio file
                    file_uuid = str(uuid.uuid4())
                    filename = f"{verse_ref}_{file_uuid}.m4a"
                    
                    # Create temporary audio file
                    temp_audio_path = f"temp_{asset_id}.m4a"
                    if self.generate_audio_v3(verse_text, temp_audio_path, voice_id):
                        # Upload to storage with full path
                        storage_path = f"{content_folder}/{filename}"
                        audio_url = self.upload_audio_to_storage(temp_audio_path, storage_path, bucket_name)
                        if audio_url:
                            audio_id = storage_path
                            print(f"Generated new audio for {verse_ref}: {audio_id}")
                            
                            # Record the audio file creation
                            if self.session_recorder:
                                self.session_recorder.add_record('audio_files', storage_path, {
                                    'bucket': bucket_name,
                                    'path': storage_path
                                })
                        
                        # Clean up temp file
                        if os.path.exists(temp_audio_path):
                            os.remove(temp_audio_path)
            
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
            
            # Add tags
            for tag_name in (
                f"livro:{formatted_book}",
                f"capítulo:{chapter}",
                f"versículo:{verse}"
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
    
    def run(self):
        """Main execution method"""
        # Get project data
        project_file = self.config['project_file']
        with open(project_file, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
        
        # Scripture reference configuration
        scripture_config = self.config.get('scripture_reference', {})
        
        # Process languages
        lang_map = {}
        for lang in project_data['languages']:
            lang_id = upsert_language(self.supabase, lang)
            lang_map[lang['english_name']] = lang_id
        
        # Fetch any additional languages from DB
        for proj in project_data['projects']:
            for lang_name in (proj['source_language_english_name'], proj['target_language_english_name']):
                if lang_name not in lang_map:
                    resp = self.supabase.table('language') \
                        .select('id') \
                        .eq('english_name', lang_name) \
                        .execute()
                    if not resp.data:
                        raise RuntimeError(f"Language {lang_name} not found in DB")
                    lang_map[lang_name] = resp.data[0]['id']
        
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
                
                # Add quest-level tags
                for tag_name in quest.get('additional_tags', []):
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
                        
                        # Record the creation
                        if self.session_recorder:
                            self.session_recorder.add_record('quest_tag_links', f"{quest_id}_{tag_id}", {
                                'quest_id': quest_id,
                                'tag_id': tag_id
                            })
        
        print("Processing complete!")


def delete_session(record_file: str):
    """Delete all records created in a session based on the record file"""
    print(f"\nDeleting session from record file: {record_file}")
    
    if not os.path.exists(record_file):
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
    CONFIG_FILE = "config.json"  # Change this to your desired config file path
    
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