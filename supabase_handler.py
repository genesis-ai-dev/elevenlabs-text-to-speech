#!/usr/bin/env python3
"""
Supabase Handler Module
Handles all database interactions with Supabase
"""

import os
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)


class SupabaseHandler:
    """Handles all Supabase database operations"""
    
    def __init__(self):
        """Initialize Supabase client"""
        load_dotenv()
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in your .env")
        self.client = create_client(url, key)
    
    def upsert_language(self, lang: Dict[str, Any]) -> str:
        """Upsert a language and return its ID"""
        # Check if language exists
        resp = self.client.table('language') \
            .select('id') \
            .eq('iso639_3', lang['iso639_3']) \
            .execute()
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        resp = self.client.table('language') \
            .insert({
                'native_name': lang['native_name'],
                'english_name': lang['english_name'],
                'iso639_3': lang['iso639_3'],
                'locale': lang['locale'],
                'ui_ready': lang['ui_ready']
            }, returning='representation') \
            .execute()
        return resp.data[0]['id']
    
    def upsert_project(self, proj: Dict[str, Any], lang_map: Dict[str, str]) -> str:
        """Upsert a project and return its ID"""
        # Check if project exists by name only
        resp = self.client.table('project') \
            .select('id') \
            .eq('name', proj['name']) \
            .execute()
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        resp = self.client.table('project') \
            .insert({
                'name': proj['name'],
                'description': proj.get('description', ''),
                'source_language_id': lang_map[proj['source_language_english_name']],
                'target_language_id': lang_map[proj['target_language_english_name']]
            }, returning='representation') \
            .execute()
        return resp.data[0]['id']
    
    def upsert_quest(self, quest: Dict[str, Any], project_id: str) -> str:
        """Upsert a quest and return its ID"""
        # Check if quest exists
        resp = self.client.table('quest') \
            .select('id') \
            .eq('name', quest['name']) \
            .eq('project_id', project_id) \
            .execute()
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        resp = self.client.table('quest') \
            .insert({
                'name': quest['name'],
                'description': quest.get('description', ''),
                'project_id': project_id
            }, returning='representation') \
            .execute()
        return resp.data[0]['id']
    
    def get_or_create_tag(self, tag_name: str, cache: Optional[Dict[str, str]] = None) -> str:
        """Get or create a tag by name, return its ID"""
        # Check cache first
        if cache and tag_name in cache:
            return cache[tag_name]
            
        # Check if tag exists
        resp = self.client.table('tag') \
            .select('id') \
            .eq('name', tag_name) \
            .execute()
        
        if resp.data:
            tag_id = resp.data[0]['id']
            if cache is not None:
                cache[tag_name] = tag_id
            return tag_id
            
        # If not exists, insert
        resp = self.client.table('tag') \
            .insert({'name': tag_name}, returning='representation') \
            .execute()
        tag_id = resp.data[0]['id']
        if cache is not None:
            cache[tag_name] = tag_id
        return tag_id
    
    def upsert_asset(self, name: str, source_language_id: str) -> str:
        """Create or get an asset and return its ID"""
        # Check if asset exists
        resp = self.client.table('asset') \
            .select('id') \
            .eq('name', name) \
            .eq('source_language_id', source_language_id) \
            .execute()
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        resp = self.client.table('asset') \
            .insert({
                'name': name,
                'source_language_id': source_language_id,
                'created_at': datetime.now(timezone.utc).isoformat()
            }, returning='representation') \
            .execute()
        return resp.data[0]['id']
    
    def upsert_asset_content_link(self, asset_id: str, text: str, audio_id: Optional[str] = None):
        """Create or update asset content link"""
        # Check if content link exists
        existing = self.client.table('asset_content_link') \
            .select('id') \
            .eq('asset_id', asset_id) \
            .execute()
        
        if existing.data:
            # Update existing
            self.client.table('asset_content_link') \
                .update({
                    'text': text,
                    'audio_id': audio_id
                }) \
                .eq('asset_id', asset_id) \
                .execute()
        else:
            # Create new
            self.client.table('asset_content_link') \
                .insert({
                    'asset_id': asset_id,
                    'text': text,
                    'audio_id': audio_id
                }) \
                .execute()
    
    def upsert_quest_asset_link(self, quest_id: str, asset_id: str):
        """Create quest-asset link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('quest_asset_link') \
            .select('quest_id') \
            .eq('quest_id', quest_id) \
            .eq('asset_id', asset_id) \
            .execute()
        
        if not existing.data:
            self.client.table('quest_asset_link') \
                .insert({
                    'quest_id': quest_id,
                    'asset_id': asset_id
                }) \
                .execute()
    
    def upsert_asset_tag_link(self, asset_id: str, tag_id: str):
        """Create asset-tag link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('asset_tag_link') \
            .select('asset_id') \
            .eq('asset_id', asset_id) \
            .eq('tag_id', tag_id) \
            .execute()
        
        if not existing.data:
            self.client.table('asset_tag_link') \
                .insert({
                    'asset_id': asset_id,
                    'tag_id': tag_id
                }) \
                .execute()
    
    def upsert_quest_tag_link(self, quest_id: str, tag_id: str):
        """Create quest-tag link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('quest_tag_link') \
            .select('quest_id') \
            .eq('quest_id', quest_id) \
            .eq('tag_id', tag_id) \
            .execute()
        
        if not existing.data:
            self.client.table('quest_tag_link') \
                .insert({
                    'quest_id': quest_id,
                    'tag_id': tag_id
                }) \
                .execute()
    
    def upload_audio_to_storage(self, file_path: str, storage_path: str, bucket_name: str) -> Optional[str]:
        """Upload audio file to Supabase storage"""
        try:
            with open(file_path, 'rb') as f:
                response = self.client.storage.from_(bucket_name).upload(
                    storage_path,
                    f.read(),
                    file_options={"content-type": "audio/mpeg"}
                )
            
            # Get public URL
            public_url = self.client.storage.from_(bucket_name).get_public_url(storage_path)
            return public_url
            
        except Exception as e:
            logger.error(f"Error uploading audio to storage: {str(e)}")
            return None
    
    def find_existing_audio(self, content_folder: str, verse_ref: str, lang_code: str, voice: str) -> Optional[str]:
        """Find existing audio file matching the criteria"""
        existing_audio = self.client.table('asset_content_link') \
            .select('audio_id') \
            .like('audio_id', f'{content_folder}/{verse_ref}_{lang_code}_{voice}_%') \
            .limit(1) \
            .execute()
        
        if existing_audio.data and existing_audio.data[0]['audio_id']:
            return existing_audio.data[0]['audio_id']
        return None
    
    def get_language_by_name(self, english_name: str) -> Optional[str]:
        """Get language ID by English name"""
        resp = self.client.table('language') \
            .select('id') \
            .eq('english_name', english_name) \
            .execute()
        
        if resp.data:
            return resp.data[0]['id']
        return None 