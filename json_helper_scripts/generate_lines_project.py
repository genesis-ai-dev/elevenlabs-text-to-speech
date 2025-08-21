#!/usr/bin/env python3
"""
Generate a lines project file that splits lines into groups of 100
"""

import json
import math

def generate_lines_project(total_lines=7958, group_size=100, output_file="unified_config_project_files/lines_project_7958_eng_tpi.json"):
    """Generate a project file with quests for every group_size lines"""
    
    # Calculate number of groups
    num_groups = math.ceil(total_lines / group_size)
    
    # Base project structure
    project_data = {
        "languages": [
            {
                "native_name": "Tok Pisin",
                "english_name": "Tok Pisin",
                "iso639_3": "tpi",
                "locale": "tpi-PG",
                "ui_ready": False
            }
        ],
        "projects": [
            {
                "name": "English Sentences to Tok Pisin",
                "description": f"Collection of {total_lines:,} English sentences to Tok Pisin",
                "source_language_english_name": "English",
                "target_language_english_name": "Tok Pisin",
                "private": False,
                "quests": []
            }
        ]
    }
    
    # Generate quests
    for i in range(num_groups):
        start_line = i * group_size + 1
        end_line = min((i + 1) * group_size, total_lines)
        
        
        quest = {
            "name": f"Sentences {start_line}-{end_line}",
            "description": f"Sentences {start_line} to {end_line}",
            "additional_tags": [
                f"module:{i + 1}",
                f"group:{(i // 10) + 1}"  # Super-groups of 10 modules
            ],
            "line_ranges": [
                [start_line, end_line]
            ]
        }
        
        project_data["projects"][0]["quests"].append(quest)
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, indent=2, ensure_ascii=False)
    
    print(f"Generated project file: {output_file}")
    print(f"Total lines: {total_lines:,}")
    print(f"Group size: {group_size}")
    print(f"Number of quests: {num_groups}")
    print(f"Last quest covers lines {(num_groups - 1) * group_size + 1}-{total_lines}")


if __name__ == "__main__":
    generate_lines_project() 