#!/usr/bin/env python3
"""
Simple script to download all audio files from Supabase storage
No config files needed - just run it!
"""

import os
import asyncio
import aiohttp
from datetime import datetime
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
MAX_CONCURRENT = 10


async def download_file(session, url, filepath):
    """Download a single file"""
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.read()
            
            with open(filepath, 'wb') as f:
                f.write(content)
            
            return True
    except Exception as e:
        print(f"Failed to download {os.path.basename(filepath)}: {e}")
        return False


async def download_all():
    """Download all files from storage"""
    print(f"Fetching file list from Supabase...")
    
    # Get ALL files with pagination
    all_files = []
    limit = 1000  # Max items per request
    offset = 0
    
    while True:
        # Get batch of files
        files = supabase.storage.from_(BUCKET_NAME).list(
            CONTENT_FOLDER,
            {"limit": limit, "offset": offset}
        )
        
        if not files:
            break
            
        all_files.extend(files)
        print(f"Fetched {len(all_files)} files so far...", end='\r')
        
        # If we got less than limit, we've reached the end
        if len(files) < limit:
            break
            
        offset += limit
    
    if not all_files:
        print("No files found!")
        return
    
    print(f"\nFound {len(all_files)} total files to download")
    
    # Create download folder
    download_folder = f"audio_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(download_folder, exist_ok=True)
    
    # Prepare downloads
    downloads = []
    for file_info in all_files:
        filename = file_info['name']
        file_path = f"{CONTENT_FOLDER}/{filename}"
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
        local_path = os.path.join(download_folder, filename)
        downloads.append((url, local_path))
    
    print(f"\nDownloading to: {download_folder}/")
    
    # Download with progress counter
    success_count = 0
    total = len(downloads)
    
    print(f"Starting download of {total} files...")
    print("This may take a while...\n")
    
    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async def download_with_progress(session, url, filepath, index):
        async with semaphore:
            success = await download_file(session, url, filepath)
            if success:
                nonlocal success_count
                success_count += 1
            
            # Show progress with percentage
            completed = index + 1
            percentage = (completed / total) * 100
            print(f"Progress: {completed}/{total} files ({percentage:.1f}%) - {success_count} successful", end='\r')
            return success
    
    # Download all files
    async with aiohttp.ClientSession() as session:
        tasks = [
            download_with_progress(session, url, filepath, i) 
            for i, (url, filepath) in enumerate(downloads)
        ]
        await asyncio.gather(*tasks)
    
    print(f"\n\nDownload complete!")
    print(f"Successfully downloaded: {success_count}/{total} files")
    print(f"Files saved to: {download_folder}/")


if __name__ == "__main__":
    # Run the download
    asyncio.run(download_all()) 