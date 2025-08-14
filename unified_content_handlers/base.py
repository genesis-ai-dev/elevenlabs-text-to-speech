#!/usr/bin/env python3
"""
Base Content Handler
Abstract base class for different content types (Bible verses, lines, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any


class ContentHandler(ABC):
    """Abstract base class for content handlers"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration"""
        self.config = config
    
    @abstractmethod
    def get_content_items(self, quest_config: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Get content items for a quest
        
        Args:
            quest_config: Quest configuration containing content references
            
        Returns:
            List of tuples (reference, text)
        """
        pass
    
    @abstractmethod
    def format_asset_name(self, reference: str, language: str) -> str:
        """
        Format the asset name for display
        
        Args:
            reference: The content reference (e.g., verse ref or line number)
            language: The source language
            
        Returns:
            Formatted asset name
        """
        pass
    
    @abstractmethod
    def get_tags(self, reference: str) -> List[str]:
        """
        Get tags for a content item
        
        Args:
            reference: The content reference
            
        Returns:
            List of tag names
        """
        pass 