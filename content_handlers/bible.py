#!/usr/bin/env python3
"""
Bible Content Handler
Handles Bible verse content using ScriptureReference
"""

from typing import List, Tuple, Dict, Any
from .base import ContentHandler
from ScriptureReference import ScriptureReference
from supabase_upload_quests import load_book_names, get_localized_book_name


class BibleContentHandler(ContentHandler):
    """Handler for Bible verse content"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Load book names if localization is enabled
        self.book_names_data = {}
        if self.config.get('book_abbreviations', {}).get('use_localized', False):
            self.book_names_data = load_book_names()
        
        # Get scripture reference config
        self.scripture_config = self.config.get('scripture_reference', {
            'bible_filename': 'source_texts/brazilian_portuguese_translation_4.txt',
            'source_type': 'local_ebible',
            'versification': 'eng'
        })
    
    def get_content_items(self, quest_config: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Get Bible verses for a quest"""
        items = []
        
        # Process verse ranges
        for start_ref, end_ref in quest_config.get('verse_ranges', []):
            sr = ScriptureReference(
                start_ref, 
                end_ref, 
                self.scripture_config['bible_filename'],
                self.scripture_config['source_type'],
                self.scripture_config.get('versification', 'eng')
            )
            
            for verse_ref, verse_text in sr.verses:
                items.append((verse_ref, verse_text))
        
        return items
    
    def format_asset_name(self, reference: str, language: str) -> str:
        """Format Bible verse reference for display"""
        # Parse reference (e.g., "JHN_1_1" -> "John 1:1")
        book_code, chapter, verse = reference.split('_', 2)
        
        # Get localized book name if configured
        book_abbr_config = self.config.get('book_abbreviations', {})
        if book_abbr_config.get('use_localized', False):
            formatted_book = get_localized_book_name(
                book_code, 
                language, 
                self.book_names_data
            )
        else:
            formatted_book = book_code.title()
        
        return f"{formatted_book} {chapter}:{verse}"
    
    def get_tags(self, reference: str) -> List[str]:
        """Get tags for a Bible verse"""
        book_code, chapter, verse = reference.split('_', 2)
        
        # Get localized book name
        book_abbr_config = self.config.get('book_abbreviations', {})
        if book_abbr_config.get('use_localized', False):
            # Assuming source language is passed somehow, for now use default
            formatted_book = get_localized_book_name(
                book_code, 
                'Brazilian Portuguese',  # This should come from context
                self.book_names_data
            )
        else:
            formatted_book = book_code.title()
        
        # Get tag labels from config
        tag_labels = self.config.get('tag_labels', {
            'book': 'book',
            'chapter': 'chapter', 
            'verse': 'verse'
        })
        
        return [
            f"{tag_labels['book']}:{formatted_book}",
            f"{tag_labels['chapter']}:{chapter}",
            f"{tag_labels['verse']}:{verse}"
        ] 