#!/usr/bin/env python3
"""
Supabase Handler Module
Handles all database interactions with Supabase
"""

import os
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import time
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

    def rpc(self, function_name: str, params: Dict[str, Any]) -> Optional[Any]:
        """Call a Postgres function via Supabase RPC, return data or None on failure"""
        try:
            resp = self.client.rpc(function_name, params).execute()
            return getattr(resp, 'data', None)
        except Exception as e:
            logger.warning(f"RPC call failed: {function_name}({params}): {e}")
            return None

    def rebuild_quest_closure(self, quest_id: str) -> None:
        """Invoke server-side rebuild for a single quest closure if available"""
        self.rpc('rebuild_single_quest_closure', {'quest_id_param': quest_id})

    def rebuild_project_closure(self, project_id: str) -> None:
        """Invoke server-side rebuild for a single project closure if available"""
        self.rpc('rebuild_single_project_closure', {'project_id_param': project_id})

    def execute_with_retry(self, builder, retries: int = 6, base_delay: float = 0.5):
        """Execute a PostgREST request builder with retry on transient errors (HTTP/2 disconnects, 5xx, timeouts)."""
        attempt = 0
        while True:
            try:
                return builder.execute()
            except Exception as e:
                message = str(e)
                transient_markers = [
                    '502', '503', '504', 'temporarily', 'Bad Gateway',
                    'ConnectionTerminated', 'RemoteProtocolError', 'Stream', 'disconnect',
                    'timeout', 'TLS', 'EOF', 'Server disconnected'
                ]
                is_transient = any(mark in message for mark in transient_markers)
                if attempt < retries and is_transient:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Transient Supabase error, retrying in {delay:.2f}s (attempt {attempt+1}/{retries+1}): {e}")
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise
    
    def upsert_language(self, lang: Dict[str, Any]) -> str:
        """Upsert a language and return its ID"""
        # Check if language exists
        resp = self.client.table('language') \
            .select('id') \
            .eq('iso639_3', lang['iso639_3']) \
            
        resp = self.execute_with_retry(resp)
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        builder = self.client.table('language') \
            .insert({
                'native_name': lang['native_name'],
                'english_name': lang['english_name'],
                'iso639_3': lang['iso639_3'],
                'locale': lang['locale'],
                'ui_ready': lang['ui_ready']
            }, returning='representation')
        resp2 = self.execute_with_retry(builder)
        return resp2.data[0]['id']
    
    def upsert_project(self, proj: Dict[str, Any], lang_map: Dict[str, str]) -> str:
        """Upsert a project and return its ID.
        Sets legacy source_language_id/target_language_id on project record for compatibility.
        If multiple sources are provided, the first is used for the project field.
        """
        resp = self.client.table('project') \
            .select('id') \
            .eq('name', proj['name']) \
            
        resp = self.execute_with_retry(resp)
        
        if resp.data:
            return resp.data[0]['id']
        
        # Determine legacy fields
        source_names = proj.get('source_language_english_name')
        if isinstance(source_names, list):
            first_source_name = source_names[0]
        else:
            first_source_name = source_names
        target_name = proj.get('target_language_english_name')
        
        builder = self.client.table('project') \
            .insert({
                'name': proj['name'],
                'description': proj.get('description', ''),
                'source_language_id': lang_map[first_source_name] if first_source_name else None,
                'target_language_id': lang_map[target_name] if target_name else None
            }, returning='representation')
        resp2 = self.execute_with_retry(builder)
        return resp2.data[0]['id']

    def upsert_project_language_link(self, project_id: str, language_id: str, language_type: str) -> None:
        """Link a language to a project as 'source' or 'target' in project_language_link"""
        existing = self.client.table('project_language_link') \
            .select('project_id') \
            .eq('project_id', project_id) \
            .eq('language_id', language_id) \
            .eq('language_type', language_type) \
            
        existing = self.execute_with_retry(existing)
        
        if not existing.data:
            builder = self.client.table('project_language_link') \
                .insert({
                    'project_id': project_id,
                    'language_id': language_id,
                    'language_type': language_type
                })
            self.execute_with_retry(builder)
    
    def upsert_quest(self, quest: Dict[str, Any], project_id: str) -> str:
        """Upsert a quest and return its ID"""
        # Check if quest exists
        resp = self.client.table('quest') \
            .select('id') \
            .eq('name', quest['name']) \
            .eq('project_id', project_id) \
            
        resp = self.execute_with_retry(resp)
        
        if resp.data:
            return resp.data[0]['id']
            
        # If not exists, insert
        builder = self.client.table('quest') \
            .insert({
                'name': quest['name'],
                'description': quest.get('description', ''),
                'project_id': project_id
            }, returning='representation')
        resp2 = self.execute_with_retry(builder)
        return resp2.data[0]['id']
    
    def get_or_create_tag(self, tag_name: str, cache: Optional[Dict[str, str]] = None) -> str:
        """Get or create a tag by name, return its ID"""
        # Check cache first
        if cache and tag_name in cache:
            return cache[tag_name]
            
        # Check if tag exists
        resp = self.client.table('tag') \
            .select('id') \
            .eq('name', tag_name) \
            
        resp = self.execute_with_retry(resp)
        
        if resp.data:
            tag_id = resp.data[0]['id']
            if cache is not None:
                cache[tag_name] = tag_id
            return tag_id
            
        # If not exists, insert
        builder = self.client.table('tag') \
            .insert({'name': tag_name}, returning='representation')
        resp2 = self.execute_with_retry(builder)
        tag_id = resp2.data[0]['id']
        if cache is not None:
            cache[tag_name] = tag_id
        return tag_id
    
    def upsert_asset(self, name: str, legacy_source_language_id: Optional[str] = None, *, force_new: bool = False) -> str:
        """Create or get an asset and return its ID.
        If force_new is True, always insert a new row even if an asset with the same name exists.
        Sets legacy source_language_id for compatibility when provided."""
        if not force_new:
            resp = self.client.table('asset') \
                .select('id') \
                .eq('name', name)
            resp = self.execute_with_retry(resp)
            if resp.data:
                return resp.data[0]['id']
        
        insert_payload = {
            'name': name,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        if legacy_source_language_id:
            insert_payload['source_language_id'] = legacy_source_language_id
        
        builder = self.client.table('asset') \
            .insert(insert_payload, returning='representation')
        resp2 = self.execute_with_retry(builder)
        return resp2.data[0]['id']
    
    def upsert_asset_content_link(self, asset_id: str, text: str, source_language_id: str, audio_id: Optional[str] = None):
        """Create or update asset content link per source language"""
        existing = self.client.table('asset_content_link') \
            .select('id') \
            .eq('asset_id', asset_id) \
            .eq('source_language_id', source_language_id) \
            
        existing = self.execute_with_retry(existing)
        
        if existing.data:
            builder = self.client.table('asset_content_link') \
                .update({
                    'text': text,
                    'audio_id': audio_id,
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }) \
                .eq('id', existing.data[0]['id'])
            self.execute_with_retry(builder)
        else:
            builder = self.client.table('asset_content_link') \
                .insert({
                    'asset_id': asset_id,
                    'source_language_id': source_language_id,
                    'text': text,
                    'audio_id': audio_id,
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
            self.execute_with_retry(builder)
    
    def upsert_quest_asset_link(self, quest_id: str, asset_id: str):
        """Create quest-asset link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('quest_asset_link') \
            .select('quest_id') \
            .eq('quest_id', quest_id) \
            .eq('asset_id', asset_id) \
            
        existing = self.execute_with_retry(existing)
        
        if not existing.data:
            builder = self.client.table('quest_asset_link') \
                .insert({
                    'quest_id': quest_id,
                    'asset_id': asset_id
                })
            self.execute_with_retry(builder)
    
    def upsert_asset_tag_link(self, asset_id: str, tag_id: str):
        """Create asset-tag link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('asset_tag_link') \
            .select('asset_id') \
            .eq('asset_id', asset_id) \
            .eq('tag_id', tag_id) \
            
        existing = self.execute_with_retry(existing)
        
        if not existing.data:
            builder = self.client.table('asset_tag_link') \
                .insert({
                    'asset_id': asset_id,
                    'tag_id': tag_id
                })
            self.execute_with_retry(builder)
    
    def upsert_quest_tag_link(self, quest_id: str, tag_id: str):
        """Create quest-tag link if it doesn't exist"""
        # Check if link exists
        existing = self.client.table('quest_tag_link') \
            .select('quest_id') \
            .eq('quest_id', quest_id) \
            .eq('tag_id', tag_id) \
            
        existing = self.execute_with_retry(existing)
        
        if not existing.data:
            builder = self.client.table('quest_tag_link') \
                .insert({
                    'quest_id': quest_id,
                    'tag_id': tag_id
                })
            self.execute_with_retry(builder)
    
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
    
    def find_existing_audio(self, content_folder: str, verse_ref: str, lang_code: str, voice: str, source_language_id: Optional[str] = None) -> Optional[str]:
        """Find existing audio file matching the criteria, optionally filtered by source language"""
        query = self.client.table('asset_content_link') \
            .select('audio_id, source_language_id') \
            .like('audio_id', f'{content_folder}/{verse_ref}_{lang_code}_{voice}_%') \
            .limit(1)
        if source_language_id:
            query = query.eq('source_language_id', source_language_id)
        existing_audio = self.execute_with_retry(query)
        
        if existing_audio.data and existing_audio.data[0]['audio_id']:
            return existing_audio.data[0]['audio_id']
        return None
    
    def get_language_by_name(self, english_name: str) -> Optional[str]:
        """Get language ID by English name"""
        resp = self.client.table('language') \
            .select('id') \
            .eq('english_name', english_name) \
            
        resp = self.execute_with_retry(resp)
        
        if resp.data:
            return resp.data[0]['id']
        return None 

    # -------- Project-scoped asset helpers --------
    def get_asset_by_name(self, name: str) -> Optional[str]:
        resp = self.client.table('asset') \
            .select('id') \
            .eq('name', name)
        resp = self.execute_with_retry(resp)
        if resp.data:
            return resp.data[0]['id']
        return None

    def get_asset_name_by_id(self, asset_id: str) -> Optional[str]:
        resp = self.client.table('asset') \
            .select('name') \
            .eq('id', asset_id)
        resp = self.execute_with_retry(resp)
        if resp.data:
            return resp.data[0]['name']
        return None

    def get_asset_linked_project_ids(self, asset_id: str) -> List[str]:
        """Return distinct project_ids of quests linked to this asset."""
        # Fetch all quest_ids linked to asset
        qal = self.client.table('quest_asset_link') \
            .select('quest_id') \
            .eq('asset_id', asset_id)
        qal = self.execute_with_retry(qal)
        quest_ids = [row['quest_id'] for row in getattr(qal, 'data', []) or []]
        if not quest_ids:
            return []
        # Fetch their projects in batch
        qresp = self.client.table('quest') \
            .select('id,project_id') \
            .in_('id', quest_ids)
        qresp = self.execute_with_retry(qresp)
        projects = sorted({row['project_id'] for row in getattr(qresp, 'data', []) or []})
        return projects

    def get_or_create_project_scoped_asset(self, name: str, project_id: str, legacy_source_language_id: Optional[str] = None) -> str:
        """Return an asset id for this project. If an asset with the same name exists but is linked to other projects, create a new asset."""
        existing_id = self.get_asset_by_name(name)
        if existing_id:
            linked_projects = self.get_asset_linked_project_ids(existing_id)
            # Reuse only if already and exclusively used by this project
            if (len(linked_projects) == 1 and linked_projects[0] == project_id):
                return existing_id
            # Otherwise, create a duplicate asset (same name allowed)
        return self.upsert_asset(name, legacy_source_language_id, force_new=True)