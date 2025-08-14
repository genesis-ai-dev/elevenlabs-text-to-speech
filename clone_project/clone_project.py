#!/usr/bin/env python3
"""
Project Cloner
Clones an existing project with all its quests, assets, and relationships
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from time import sleep

from unified_content_handlers.supabase_handler import SupabaseHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionRecorder:
    """Records all database operations for potential rollback"""
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"clone_session_record_{self.timestamp}.json"
        self.filepath = None
        self.records = {
            "timestamp": self.timestamp,
            "operation": "project_clone",
            "source_project": None,
            "languages": [],
            "projects": [],
            "quests": [],
            "assets": [],
            "asset_content_links": [],
            "quest_asset_links": [],
            "asset_tag_links": [],
            "quest_tag_links": []
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
        logger.info(f"Clone session record initialized: {self.filepath}")
    
    def _write_to_file(self):
        """Write current records to file"""
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2)
    
    def set_source_project(self, project_name: str):
        """Set the source project being cloned"""
        self.records["source_project"] = project_name
        self._write_to_file()
    
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
        print(f"\nClone session record saved to: {self.filepath}")
        return self.filepath


class ProjectCloner:
    """Handles cloning of projects with all relationships"""
    
    def __init__(self, config_file: str):
        """Initialize with configuration from JSON file"""
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Validate configuration
        required_fields = ['source_project_name', 'target_language_native_name', 'new_project_description']
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Configuration must contain '{field}'")
        
        # Initialize session recorder
        self.session_recorder = SessionRecorder()
        self.session_recorder.set_source_project(self.config['source_project_name'])
        
        # Initialize Supabase handler
        self.supabase = SupabaseHandler()
        
        # Mapping tables for cloning
        self.quest_mapping = {}  # old_quest_id -> new_quest_id
        self.asset_mapping = {}  # old_asset_id -> new_asset_id
        
        # Connection management
        self.request_count = 0
        self.max_requests_per_connection = 5000  # Reset connection before hitting limits
        
        logger.info(f"Initialized project cloner for source: {self.config['source_project_name']}")
    
    def _execute_with_retry(self, func, max_retries=3, backoff_factor=1):
        """Execute a function with retry logic for connection errors"""
        for attempt in range(max_retries):
            try:
                # Check if we need to reset the connection
                self.request_count += 1
                if self.request_count >= self.max_requests_per_connection:
                    logger.info("Resetting connection to avoid HTTP/2 stream limits...")
                    # Recreate the Supabase client to get a fresh connection
                    self.supabase = SupabaseHandler()
                    self.request_count = 0
                
                return func()
            except Exception as e:
                error_str = str(e)
                # Check for connection-related errors
                if any(err in error_str for err in ['ConnectionTerminated', 'RemoteProtocolError', 'ConnectionError']):
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"Connection error on attempt {attempt + 1}, retrying in {wait_time}s: {error_str}")
                        sleep(wait_time)
                        # Reset connection for next attempt
                        self.supabase = SupabaseHandler()
                        self.request_count = 0
                        continue
                raise
        raise Exception(f"Failed after {max_retries} attempts")
    
    def get_or_create_target_language(self) -> str:
        """Get or create the target language"""
        native_name = self.config['target_language_native_name']
        
        # Check if language exists by native name
        resp = self.supabase.client.table('language') \
            .select('*') \
            .eq('native_name', native_name) \
            .execute()
        
        if resp.data:
            logger.info(f"Using existing language: {native_name}")
            return resp.data[0]['id']
        
        # Create new language with defaults
        english_name = self.config.get('target_language_english_name', native_name)
        iso639_3 = self.config.get('target_language_iso639_3', 'und')  # 'und' for undetermined
        locale = self.config.get('target_language_locale', '')
        ui_ready = self.config.get('target_language_ui_ready', False)
        
        resp = self.supabase.client.table('language') \
            .insert({
                'native_name': native_name,
                'english_name': english_name,
                'iso639_3': iso639_3,
                'locale': locale,
                'ui_ready': ui_ready
            }, returning='representation') \
            .execute()
        
        lang_id = resp.data[0]['id']
        logger.info(f"Created new language: {native_name} (ID: {lang_id})")
        
        self.session_recorder.add_record('languages', lang_id, {
            'native_name': native_name,
            'english_name': english_name,
            'iso639_3': iso639_3
        })
        
        return lang_id
    
    def clone_project(self):
        """Main method to clone the project"""
        start_time = time.time()
        
        try:
            # 1. Find source project
            source_project = self.find_source_project()
            if not source_project:
                raise ValueError(f"Source project '{self.config['source_project_name']}' not found")
            
            logger.info(f"Found source project: {source_project['name']} (ID: {source_project['id']})")
            
            # 2. Get or create target language
            target_language_id = self.get_or_create_target_language()
            
            # 3. Create new project
            new_project_id = self.create_new_project(source_project, target_language_id)
            
            # 4. Clone all quests
            self.clone_quests(source_project['id'], new_project_id)
            
            # 5. Clone all assets and their relationships
            self.clone_assets_and_relationships(source_project['id'])
            
            # Save session record
            self.session_recorder.save()
            
            # Display execution time
            end_time = time.time()
            total_time = end_time - start_time
            
            if total_time < 60:
                time_str = f"{total_time:.2f} seconds"
            else:
                minutes = total_time / 60
                time_str = f"{minutes:.2f} minutes"
            
            print(f"\nProject cloned successfully!")
            print(f"Total execution time: {time_str}")
            print(f"\nNew project created: {self.config.get('new_project_name', source_project['name'] + ' (Clone)')}")
            print(f"Total quests cloned: {len(self.quest_mapping)}")
            print(f"Total assets cloned: {len(self.asset_mapping)}")
            
        except Exception as e:
            logger.error(f"Error during cloning: {str(e)}")
            self.session_recorder.save()
            raise
    
    def find_source_project(self) -> Optional[Dict[str, Any]]:
        """Find the source project by name"""
        resp = self.supabase.client.table('project') \
            .select('*') \
            .eq('name', self.config['source_project_name']) \
            .execute()
        
        if resp.data:
            return resp.data[0]
        return None
    
    def create_new_project(self, source_project: Dict[str, Any], target_language_id: str) -> str:
        """Create the new cloned project"""
        new_name = self.config.get('new_project_name', f"{source_project['name']} (Clone)")
        
        # Check if project with new name already exists
        existing = self.supabase.client.table('project') \
            .select('id') \
            .eq('name', new_name) \
            .execute()
        
        if existing.data:
            raise ValueError(f"Project with name '{new_name}' already exists")
        
        # Create new project
        resp = self.supabase.client.table('project') \
            .insert({
                'name': new_name,
                'description': self.config['new_project_description'],
                'source_language_id': source_project['source_language_id'],
                'target_language_id': target_language_id,
                'private': self.config.get('private', source_project.get('private', False))
            }, returning='representation') \
            .execute()
        
        new_project_id = resp.data[0]['id']
        logger.info(f"Created new project: {new_name} (ID: {new_project_id})")
        
        self.session_recorder.add_record('projects', new_project_id, {
            'name': new_name,
            'source_language_id': source_project['source_language_id'],
            'target_language_id': target_language_id
        })
        
        return new_project_id
    
    def clone_quests(self, source_project_id: str, new_project_id: str):
        """Clone all quests from source to new project"""
        # Fetch quests with pagination to handle projects with >1000 quests
        all_quests = []
        limit = 1000
        offset = 0
        
        while True:
            resp = self.supabase.client.table('quest') \
                .select('*') \
                .eq('project_id', source_project_id) \
                .range(offset, offset + limit - 1) \
                .execute()
            
            batch = resp.data
            if not batch:
                break
                
            all_quests.extend(batch)
            
            # If we got less than the limit, we've reached the end
            if len(batch) < limit:
                break
                
            offset += limit
        
        logger.info(f"Found {len(all_quests)} quests to clone")
        
        for quest in all_quests:
            # Create new quest
            new_quest_resp = self.supabase.client.table('quest') \
                .insert({
                    'name': quest['name'],
                    'description': quest.get('description', ''),
                    'project_id': new_project_id
                }, returning='representation') \
                .execute()
            
            new_quest_id = new_quest_resp.data[0]['id']
            self.quest_mapping[quest['id']] = new_quest_id
            
            self.session_recorder.add_record('quests', new_quest_id, {
                'name': quest['name'],
                'project_id': new_project_id,
                'original_quest_id': quest['id']
            })
            
            # Clone quest tags
            self.clone_quest_tags(quest['id'], new_quest_id)
        
        logger.info(f"Cloned {len(self.quest_mapping)} quests")
    
    def clone_quest_tags(self, old_quest_id: str, new_quest_id: str):
        """Clone all tags for a quest"""
        # Get all tags for the old quest
        resp = self.supabase.client.table('quest_tag_link') \
            .select('tag_id') \
            .eq('quest_id', old_quest_id) \
            .execute()
        
        for link in resp.data:
            # Create new quest-tag link
            self.supabase.client.table('quest_tag_link') \
                .insert({
                    'quest_id': new_quest_id,
                    'tag_id': link['tag_id']
                }) \
                .execute()
            
            self.session_recorder.add_record('quest_tag_links', f"{new_quest_id}_{link['tag_id']}", {
                'quest_id': new_quest_id,
                'tag_id': link['tag_id']
            })
    
    def clone_assets_and_relationships(self, source_project_id: str):
        """Clone all assets and their relationships"""
        # Fetch quest_asset_links for each quest individually to avoid pagination limits
        all_quest_asset_links = []
        unique_asset_ids = set()
        
        logger.info(f"Fetching assets for {len(self.quest_mapping)} quests...")
        
        # Process each quest individually to avoid the 1000-row limit
        for old_quest_id in self.quest_mapping.keys():
            resp = self.supabase.client.table('quest_asset_link') \
                .select('asset_id, quest_id') \
                .eq('quest_id', old_quest_id) \
                .execute()
            
            quest_asset_links = resp.data
            all_quest_asset_links.extend(quest_asset_links)
            
            # Collect unique asset IDs
            for link in quest_asset_links:
                unique_asset_ids.add(link['asset_id'])
        
        unique_asset_ids = list(unique_asset_ids)
        logger.info(f"Found {len(unique_asset_ids)} unique assets to clone from {len(all_quest_asset_links)} quest-asset links")
        
        # Clone each asset
        for idx, old_asset_id in enumerate(unique_asset_ids):
            if idx % 100 == 0:
                logger.info(f"Cloning assets: {idx}/{len(unique_asset_ids)} ({idx/len(unique_asset_ids)*100:.1f}%)")
            new_asset_id = self.clone_single_asset(old_asset_id)
            self.asset_mapping[old_asset_id] = new_asset_id
        
        # Create new quest-asset links
        for link in all_quest_asset_links:
            old_quest_id = link['quest_id']
            old_asset_id = link['asset_id']
            
            if old_quest_id in self.quest_mapping and old_asset_id in self.asset_mapping:
                new_quest_id = self.quest_mapping[old_quest_id]
                new_asset_id = self.asset_mapping[old_asset_id]
                
                self.supabase.client.table('quest_asset_link') \
                    .insert({
                        'quest_id': new_quest_id,
                        'asset_id': new_asset_id
                    }) \
                    .execute()
                
                self.session_recorder.add_record('quest_asset_links', f"{new_quest_id}_{new_asset_id}", {
                    'quest_id': new_quest_id,
                    'asset_id': new_asset_id
                })
        
        logger.info(f"Cloned {len(self.asset_mapping)} assets with {len(all_quest_asset_links)} relationships")
    
    def clone_single_asset(self, old_asset_id: str) -> str:
        """Clone a single asset with all its data"""
        # Get asset details
        asset_resp = self._execute_with_retry(
            lambda: self.supabase.client.table('asset')
                .select('*')
                .eq('id', old_asset_id)
                .execute()
        )
        
        if not asset_resp.data:
            raise ValueError(f"Asset {old_asset_id} not found")
        
        old_asset = asset_resp.data[0]
        
        # Create new asset
        new_asset_resp = self._execute_with_retry(
            lambda: self.supabase.client.table('asset')
                .insert({
                    'name': old_asset['name'],
                    'source_language_id': old_asset['source_language_id'],
                    'created_at': datetime.now(timezone.utc).isoformat()
                }, returning='representation')
                .execute()
        )
        
        new_asset_id = new_asset_resp.data[0]['id']
        
        self.session_recorder.add_record('assets', new_asset_id, {
            'name': old_asset['name'],
            'source_language_id': old_asset['source_language_id'],
            'original_asset_id': old_asset_id
        })
        
        # Clone asset content link
        content_resp = self._execute_with_retry(
            lambda: self.supabase.client.table('asset_content_link')
                .select('*')
                .eq('asset_id', old_asset_id)
                .execute()
        )
        
        if content_resp.data:
            old_content = content_resp.data[0]
            
            # Note: We copy the text but NOT the audio_id
            # The new project will need to generate its own audio
            self._execute_with_retry(
                lambda: self.supabase.client.table('asset_content_link')
                    .insert({
                        'asset_id': new_asset_id,
                        'text': old_content['text'],
                        'audio_id': None  # Don't copy audio
                    })
                    .execute()
            )
            
            self.session_recorder.add_record('asset_content_links', f"{new_asset_id}_content", {
                'asset_id': new_asset_id,
                'has_audio': False
            })
        
        # Clone asset tags
        tag_resp = self._execute_with_retry(
            lambda: self.supabase.client.table('asset_tag_link')
                .select('tag_id')
                .eq('asset_id', old_asset_id)
                .execute()
        )
        
        for link in tag_resp.data:
            self._execute_with_retry(
                lambda: self.supabase.client.table('asset_tag_link')
                    .insert({
                        'asset_id': new_asset_id,
                        'tag_id': link['tag_id']
                    })
                    .execute()
            )
            
            self.session_recorder.add_record('asset_tag_links', f"{new_asset_id}_{link['tag_id']}", {
                'asset_id': new_asset_id,
                'tag_id': link['tag_id']
            })
        
        return new_asset_id


def delete_clone_session(record_file: str):
    """Delete all records from a clone session using the session record file"""
    from unified_content_handlers.supabase_handler import SupabaseHandler
    
    print(f"\nDeleting clone session from: {record_file}")
    
    with open(record_file, 'r') as f:
        session_data = json.load(f)
    
    sb = SupabaseHandler()
    
    # Delete in reverse order of creation to handle dependencies
    
    # 1. Delete quest-tag links
    for link in session_data.get('quest_tag_links', []):
        try:
            sb.client.table('quest_tag_link') \
                .delete() \
                .eq('quest_id', link['quest_id']) \
                .eq('tag_id', link['tag_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting quest-tag link: {e}")
    
    # 2. Delete asset-tag links
    for link in session_data.get('asset_tag_links', []):
        try:
            sb.client.table('asset_tag_link') \
                .delete() \
                .eq('asset_id', link['asset_id']) \
                .eq('tag_id', link['tag_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting asset-tag link: {e}")
    
    # 3. Delete quest-asset links
    for link in session_data.get('quest_asset_links', []):
        try:
            sb.client.table('quest_asset_link') \
                .delete() \
                .eq('quest_id', link['quest_id']) \
                .eq('asset_id', link['asset_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting quest-asset link: {e}")
    
    # 4. Delete asset content links
    for link in session_data.get('asset_content_links', []):
        try:
            sb.client.table('asset_content_link') \
                .delete() \
                .eq('asset_id', link['asset_id']) \
                .execute()
        except Exception as e:
            print(f"Error deleting asset content link: {e}")
    
    # 5. Delete assets
    for asset in session_data.get('assets', []):
        try:
            sb.client.table('asset') \
                .delete() \
                .eq('id', asset['id']) \
                .execute()
            print(f"Deleted asset: {asset['name']}")
        except Exception as e:
            print(f"Error deleting asset {asset['id']}: {e}")
    
    # 6. Delete quests
    for quest in session_data.get('quests', []):
        try:
            sb.client.table('quest') \
                .delete() \
                .eq('id', quest['id']) \
                .execute()
            print(f"Deleted quest: {quest['name']}")
        except Exception as e:
            print(f"Error deleting quest {quest['id']}: {e}")
    
    # 7. Delete projects
    for project in session_data.get('projects', []):
        try:
            sb.client.table('project') \
                .delete() \
                .eq('id', project['id']) \
                .execute()
            print(f"Deleted project: {project['name']}")
        except Exception as e:
            print(f"Error deleting project {project['id']}: {e}")
    
    # 8. Delete languages (only if they were created in this session)
    for language in session_data.get('languages', []):
        try:
            sb.client.table('language') \
                .delete() \
                .eq('id', language['id']) \
                .execute()
            print(f"Deleted language: {language.get('native_name', language['id'])}")
        except Exception as e:
            print(f"Error deleting language {language['id']}: {e}")
    
    print("\nClone session deletion complete!")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clone a project with all its quests and assets")
    parser.add_argument('config_file', nargs='?', help='Configuration JSON file for cloning')
    parser.add_argument('--delete', metavar='SESSION_FILE', 
                       help='Delete a clone session using its record file')
    args = parser.parse_args()
    
    if args.delete:
        # Delete mode
        delete_clone_session(args.delete)
    elif args.config_file:
        # Normal cloning mode
        cloner = ProjectCloner(args.config_file)
        cloner.clone_project()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()