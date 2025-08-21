#!/usr/bin/env python3
"""
Lines Content Handler
Handles line-based content (e.g., sentences from a file)
"""

import os
from typing import List, Tuple, Dict, Any
from .base import ContentHandler


class LinesContentHandler(ContentHandler):
    """Handler for line-based content"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Get lines configuration
        self.lines_config = self.config.get('lines_reference', {})
        self.source_file = self.lines_config.get('source_file')
        
        if not self.source_file:
            raise ValueError("lines_reference.source_file is required for lines content")
        
        # Load all lines once
        self._load_lines()
    
    def _load_lines(self):
        """Load all lines from the source file"""
        if not os.path.exists(self.source_file):
            raise FileNotFoundError(f"Source file not found: {self.source_file}")
        
        with open(self.source_file, 'r', encoding='utf-8') as f:
            self.lines = [line.strip() for line in f.readlines()]
    
    def get_content_items(self, quest_config: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Get lines for a quest based on line ranges"""
        items = []
        
        # Determine ranges: if none provided, process entire file line-by-line
        ranges = quest_config.get('line_ranges')
        if not ranges:
            # Whole file, 1-indexed
            ranges = [(1, len(self.lines))]
        
        # Process line ranges
        for start_line, end_line in ranges:
            # Convert to 0-based indexing
            start_idx = start_line - 1
            end_idx = end_line  # end_line is inclusive, so no -1
            
            # Validate range
            if start_idx < 0 or end_idx > len(self.lines):
                print(f"Warning: Line range {start_line}-{end_line} is out of bounds (file has {len(self.lines)} lines)")
                continue
            
            # Extract lines
            for line_num in range(start_line, end_line + 1):
                idx = line_num - 1
                if idx < len(self.lines) and self.lines[idx]:  # Skip empty lines
                    # Reference format: "line_<number>"
                    reference = f"line_{line_num}"
                    items.append((reference, self.lines[idx]))
        
        return items
    
    def format_asset_name(self, reference: str, language: str) -> str:
        """Format line reference for display"""
        # Parse reference (e.g., "line_1" -> "1")
        _, line_num = reference.split('_', 1)
        return line_num
    
    def get_tags(self, reference: str) -> List[str]:
        """Get tags for a line"""
        _, line_num = reference.split('_', 1)
        line_num = int(line_num)
        
        # Get tag labels from config
        tag_labels = self.config.get('tag_labels', {
            'line': 'line',
            'group': 'group'
        })
        
        tags = [f"{tag_labels['line']}:{line_num}"]
        
        # Add group tags if configured
        group_size = self.lines_config.get('group_size', 100)
        if group_size > 0:
            group_num = ((line_num - 1) // group_size) + 1
            tags.append(f"{tag_labels['group']}:{group_num}")
        
        return tags 