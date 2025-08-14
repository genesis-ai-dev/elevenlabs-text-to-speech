#!/usr/bin/env python3
"""
Analyze All Session Records
Provides a summary of all session record files in the session_records directory
"""

import os
import json
from typing import Dict, List, Tuple
from datetime import datetime
from collections import defaultdict


def analyze_session_file(filepath: str) -> Dict[str, any]:
    """Analyze a single session record file and return summary data"""
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Count records by type
        record_counts = {}
        total_records = 0
        
        tables = [
            'languages', 'projects', 'quests', 'assets', 
            'asset_content_links', 'quest_asset_links',
            'asset_tag_links', 'quest_tag_links', 'tags',
            'audio_files', 'local_audio_files'
        ]
        
        for table in tables:
            if table in session_data:
                count = len(session_data[table])
                if count > 0:
                    record_counts[table] = count
                    total_records += count
        
        return {
            'timestamp': session_data.get('timestamp', 'N/A'),
            'operation': session_data.get('operation', 'unknown'),
            'source_project': session_data.get('source_project', None),
            'record_counts': record_counts,
            'total_records': total_records,
            'filename': os.path.basename(filepath)
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'filename': os.path.basename(filepath)
        }


def format_timestamp(timestamp_str: str) -> str:
    """Format timestamp for display"""
    try:
        # Parse YYYYMMDD_HHMMSS format
        dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp_str


def main():
    """Main entry point"""
    
    session_dir = 'session_records'
    
    if not os.path.exists(session_dir):
        print(f"Error: Directory '{session_dir}' not found.")
        return
    
    # Find all session record files
    session_files = []
    for filename in os.listdir(session_dir):
        if filename.endswith('.json') and (
            filename.startswith('session_record_') or 
            filename.startswith('clone_session_record_')
        ):
            filepath = os.path.join(session_dir, filename)
            session_files.append(filepath)
    
    if not session_files:
        print("No session record files found.")
        return
    
    print(f"\n{'='*80}")
    print(f"Session Records Summary")
    print(f"{'='*80}")
    print(f"\nFound {len(session_files)} session record(s)\n")
    
    # Analyze each file
    sessions = []
    for filepath in sorted(session_files):
        analysis = analyze_session_file(filepath)
        sessions.append(analysis)
    
    # Group by operation type
    by_operation = defaultdict(list)
    for session in sessions:
        if 'error' not in session:
            by_operation[session['operation']].append(session)
    
    # Display by operation type
    for operation, operation_sessions in sorted(by_operation.items()):
        print(f"\n{'-'*80}")
        print(f"Operation: {operation.upper()}")
        print(f"{'-'*80}\n")
        
        for session in sorted(operation_sessions, key=lambda x: x['timestamp'], reverse=True):
            print(f"File: {session['filename']}")
            print(f"Time: {format_timestamp(session['timestamp'])}")
            
            if session.get('source_project'):
                print(f"Source: {session['source_project']}")
            
            print(f"Total Records: {session['total_records']}")
            
            # Show breakdown
            if session['record_counts']:
                print("  Breakdown:")
                for table, count in sorted(session['record_counts'].items()):
                    table_display = table.replace('_', ' ').title()
                    print(f"    {table_display}: {count}")
            
            print()
    
    # Summary statistics
    print(f"\n{'='*80}")
    print(f"Overall Statistics")
    print(f"{'='*80}\n")
    
    total_all_records = sum(s['total_records'] for s in sessions if 'error' not in s)
    print(f"Total records across all sessions: {total_all_records:,}")
    
    # Count by table across all sessions
    table_totals = defaultdict(int)
    for session in sessions:
        if 'error' not in session:
            for table, count in session['record_counts'].items():
                table_totals[table] += count
    
    if table_totals:
        print("\nRecords by table (all sessions):")
        for table, total in sorted(table_totals.items(), key=lambda x: x[1], reverse=True):
            table_display = table.replace('_', ' ').title()
            print(f"  {table_display:.<40} {total:>8,}")
    
    # Show errors if any
    errors = [s for s in sessions if 'error' in s]
    if errors:
        print(f"\n{'-'*80}")
        print("Files with errors:")
        for session in errors:
            print(f"  {session['filename']}: {session['error']}")


if __name__ == "__main__":
    main()