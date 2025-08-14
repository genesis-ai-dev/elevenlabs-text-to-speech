import os
import glob
from dotenv import load_dotenv
from supabase import create_client, Client
from pathlib import Path

def upload_mp3s_to_supabase(folder_path, recursive=False):
    """
    Upload all MP3 files from the specified folder to Supabase storage.
    
    Args:
        folder_path (str): Path to the folder containing MP3 files
        recursive (bool): Whether to search for MP3s in subfolders
    
    Returns:
        tuple: (list of successful uploads, list of failed uploads)
    """
    # Load environment variables
    load_dotenv()
    
    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    bucket_name = os.getenv("SUPABASE_BUCKET", "assets")
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        return [], []
    
    supabase: Client = create_client(supabase_url, supabase_key)
    
    # Skip bucket creation and just use the existing bucket
    print(f"Using existing bucket: {bucket_name}")
    
    # Find all MP3 files
    pattern = os.path.join(folder_path, "**/*.mp3") if recursive else os.path.join(folder_path, "*.mp3")
    mp3_files = glob.glob(pattern, recursive=recursive)
    
    successful_uploads = []
    failed_uploads = []
    
    print(f"Found {len(mp3_files)} MP3 files to upload")
    
    # Upload each file
    for file_path in mp3_files:
        # Use Path.stem to get the filename without extension
        file_name_with_ext = os.path.basename(file_path)
        file_name_no_ext = Path(file_path).stem
        
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            # Upload to Supabase using the name without extension
            result = supabase.storage.from_(bucket_name).upload(
                path=file_name_no_ext,  # No extension here
                file=file_content,
                file_options={"content-type": "audio/mpeg"}
            )
            
            print(f"Successfully uploaded: {file_name_with_ext} as {file_name_no_ext}")
            successful_uploads.append(file_path)
            
        except Exception as e:
            print(f"Failed to upload {file_name_with_ext}: {str(e)}")
            failed_uploads.append((file_path, str(e)))
    
    # Summary
    print(f"\nUpload summary:")
    print(f"  - Successfully uploaded: {len(successful_uploads)} files")
    print(f"  - Failed to upload: {len(failed_uploads)} files")
    
    return successful_uploads, failed_uploads

if __name__ == "__main__":
    # Replace this with your folder path
    folder_path = "audio/luke_1_1-5_spapddpt"
    
    # Set to True if you want to include subfolders
    recursive = False
    
    successful, failed = upload_mp3s_to_supabase(folder_path, recursive)
    
    # Exit with appropriate code
    exit(1 if failed else 0) 


