#!/usr/bin/env python3
"""
Simple script to upload all audio files from a local folder to Supabase storage
No config files needed - just run it with the folder path!
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Get Supabase credentials from .env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Please set SUPABASE_URL and SUPABASE_KEY in your .env file")
    exit(1)

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Settings
BUCKET_NAME = "assets"
CONTENT_FOLDER = "content"


def upload_file(filepath, storage_path):
    """Upload a single file"""
    try:
        with open(filepath, 'rb') as f:
            file_data = f.read()
        
        # Always use audio/mpeg for m4a files (Supabase requirement)
        content_type = "audio/mpeg"
        
        # Upload to Supabase
        response = supabase.storage.from_(BUCKET_NAME).upload(
            storage_path,
            file_data,
            file_options={"content-type": content_type}
        )
        
        return True
    except Exception as e:
        # Check if file already exists
        if "already exists" in str(e):
            print(f"Skipped {os.path.basename(filepath)} - already exists")
        else:
            print(f"Failed to upload {os.path.basename(filepath)}: {e}")
        return False


def upload_all(folder_path):
    """Upload all files from the specified folder one at a time"""
    # Get list of files
    files = []
    for filename in os.listdir(folder_path):
        filepath = os.path.join(folder_path, filename)
        if os.path.isfile(filepath):
            files.append((filename, filepath))
    
    if not files:
        print(f"No files found in {folder_path}")
        return
    
    print(f"Found {len(files)} files to upload")
    print(f"Uploading to: {BUCKET_NAME}/{CONTENT_FOLDER}/")
    print("Uploading one file at a time for reliability...\n")
    
    # Upload files one by one
    success_count = 0
    total = len(files)
    
    for index, (filename, filepath) in enumerate(files):
        storage_path = f"{CONTENT_FOLDER}/{filename}"
        
        # Show progress before upload
        percentage = ((index + 1) / total) * 100
        print(f"Uploading {index + 1}/{total} ({percentage:.1f}%): {filename}", end='... ')
        
        # Upload the file
        success = upload_file(filepath, storage_path)
        
        if success:
            success_count += 1
            print("✓")
        else:
            print("✗")
    
    print(f"\n\nUpload complete!")
    print(f"Successfully uploaded: {success_count}/{total} files")
    if success_count < total:
        print(f"Failed/Skipped: {total - success_count} files")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python upload_all_audio_simple.py <folder_path>")
        print("Example: python upload_all_audio_simple.py audio_files_20240115_143022")
        exit(1)
    
    folder_path = sys.argv[1]
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' not found!")
        exit(1)
    
    if not os.path.isdir(folder_path):
        print(f"Error: '{folder_path}' is not a folder!")
        exit(1)
    
    # Run the upload
    upload_all(folder_path)


if __name__ == "__main__":
    main() 