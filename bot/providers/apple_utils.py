import os
import re
import asyncio
import subprocess
import zipfile
from config import Config
from bot.logger import LOGGER
from .apple_metadata import extract_apple_metadata, default_metadata

async def run_apple_downloader(url: str, output_dir: str, options: list = None, user: dict = None) -> dict:
    """
    Execute Apple Music downloader script with config file setup
    
    Args:
        url: Apple Music URL to download
        output_dir: User-specific directory to save files
        options: List of command-line options
        user: User details for progress updates
    
    Returns:
        dict: {'success': bool, 'error': str if failed}
    """
    # Create ALAC and Atmos subdirectories
    alac_dir = os.path.join(output_dir, "alac")
    atmos_dir = os.path.join(output_dir, "atmos")
    os.makedirs(alac_dir, exist_ok=True)
    os.makedirs(atmos_dir, exist_ok=True)
    
    # Create config file with user-specific paths
    config_path = os.path.join(output_dir, "config.yaml")
    
    # Dynamic configuration with user-specific paths
    config_content = f"""# Configuration for Apple Music downloader
lrc-type: "lyrics"
lrc-format: "lrc"
embed-lrc: true
save-lrc-file: true
save-artist-cover: true
save-animated-artwork: false
emby-animated-artwork: false
embed-cover: true
cover-size: 5000x5000
cover-format: original
max-memory-limit: 256
decrypt-m3u8-port: "127.0.0.1:10020"
get-m3u8-port: "127.0.0.1:20020"
get-m3u8-from-device: true
get-m3u8-mode: hires
aac-type: aac-lc
alac-max: {Config.APPLE_ALAC_QUALITY}
atmos-max: {Config.APPLE_ATMOS_QUALITY}
limit-max: 200
album-folder-format: "{{AlbumName}}"
playlist-folder-format: "{{PlaylistName}}"
song-file-format: "{{SongNumer}}. {{SongName}}"
artist-folder-format: "{{UrlArtistName}}"
explicit-choice : "[E]"
clean-choice : "[C]"
apple-master-choice : "[M]"
use-songinfo-for-playlist: false
dl-albumcover-for-playlist: false
mv-audio-type: atmos
mv-max: 2160
# USER-SPECIFIC PATHS:
alac-save-folder: {alac_dir}
atmos-save-folder: {atmos_dir}
"""
    
    with open(config_path, 'w') as config_file:
        config_file.write(config_content)
    
    LOGGER.info(f"Created Apple Music config at: {config_path}")
    
    # Build command with user-specific options
    cmd = [Config.DOWNLOADER_PATH]
    if options:
        cmd.extend(options)
    cmd.append(url)
    
    LOGGER.info(f"Running Apple downloader: {' '.join(cmd)} in {output_dir}")
    
    # Run the command
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=output_dir,  # Set working directory to user folder
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Read output in chunks to avoid buffer overrun
    stdout_chunks = []
    while True:
        chunk = await process.stdout.read(4096)  # Read 4KB chunks
        if not chunk:
            break
        stdout_chunks.append(chunk)
        
        # Process chunk for progress updates
        chunk_str = chunk.decode(errors='ignore')
        if user and 'bot_msg' in user:
            # Look for progress in the chunk
            progress_match = re.search(r'(\d+)%', chunk_str)
            if progress_match:
                try:
                    progress = int(progress_match.group(1))
                    await edit_message(
                        user['bot_msg'],
                        f"Apple Music Download: {progress}%"
                    )
                except:
                    pass
    
    # Combine all chunks
    stdout_output = b''.join(stdout_chunks).decode(errors='ignore')
    stdout_lines = stdout_output.splitlines()
    
    # Log all output lines
    for line in stdout_lines:
        LOGGER.debug(f"Apple Downloader: {line}")
    
    # Wait for process to finish
    stderr = await process.stderr.read()
    stderr = stderr.decode().strip()
    
    # Check return code
    if process.returncode != 0:
        error = stderr or "\n".join(stdout_lines)
        LOGGER.error(f"Apple downloader failed: {error}")
        return {'success': False, 'error': error}
    
    return {'success': True}

async def create_apple_zip(directory: str, user_id: int, metadata: dict) -> str:
    """
    Create zip file with descriptive name for downloads
    Args:
        directory: Path to the content directory
        user_id: Telegram user ID
        metadata: Content metadata dictionary
    Returns:
        Path to the created zip file
    """
    # Determine content type and name
    content_type = metadata.get('type', 'album').capitalize()
    content_name = metadata.get('title', 'Unknown')
    provider = metadata.get('provider', 'Apple Music')
    
    # Sanitize the content name for filesystem safety
    safe_name = re.sub(r'[\\/*?:"<>|]', "", content_name)
    safe_name = safe_name.replace(' ', '_')[:100]  # Limit length
    
    # If name is empty after sanitization, use fallback
    if not safe_name.strip():
        safe_name = f"Apple_Music_{int(time.time())}"
        LOGGER.warning(f"Empty content name after sanitization, using fallback: {safe_name}")
    
    # Create descriptive filename based on content type
    if content_type.lower() == 'album':
        zip_name = f"[{provider}] {safe_name}"
    elif content_type.lower() == 'playlist':
        zip_name = f"[{provider}] {safe_name} (Playlist)"
    elif content_type.lower() == 'artist':
        zip_name = f"[{provider}] {safe_name} (Artist)"
    elif content_type.lower() == 'video':
        zip_name = f"[{provider}] {safe_name} (Video)"
    else:
        zip_name = f"[{provider}] {safe_name}"
    
    # Create zip path in the content's directory
    zip_dir = os.path.dirname(directory)
    zip_path = os.path.join(zip_dir, f"{zip_name}.zip")
    
    # Ensure unique filename
    counter = 1
    while os.path.exists(zip_path):
        zip_path = os.path.join(zip_dir, f"{zip_name}_{counter}.zip")
        counter += 1
    
    # Create the zip file
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, directory)
                zipf.write(file_path, arcname)
    
    LOGGER.info(f"Created descriptive zip: {zip_path}")
    return zip_path
