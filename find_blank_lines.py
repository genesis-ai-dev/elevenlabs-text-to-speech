#!/usr/bin/env python3
"""
Script to find and print all blank lines in vref_eng.txt
"""

def find_blank_lines(filename='vref_eng_verses_added_1.txt'):
    """Find all blank lines in the given file and print their line numbers."""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            blank_lines = []
            
            for line_num, line in enumerate(file, 1):
                # Check if line is empty or contains only whitespace
                if not line.strip():
                    blank_lines.append(line_num)
            
            # Print results
            if blank_lines:
                print(f"Found {len(blank_lines)} blank line(s) in {filename}:")
                print(f"Line numbers: {', '.join(map(str, blank_lines))}")
            else:
                print(f"No blank lines found in {filename}")
                
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    find_blank_lines() 