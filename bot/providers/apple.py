import os
import re
import asyncio
import logging
import shutil
import mutagen
from pathlib import Path
from bot.helpers.utils import (
    send_message,
    edit_message,
    format_string,
    cleanup
)
from bot.helpers.database.pg_impl import download_history
from config import Config
from bot.logger import LOGGER

# Import from new organized modules
from .apple_utils import run_apple_downloader
from .apple_metadata import extract_apple_metadata, default_metadata

logger = logging.getLogger(__name__)

class AppleMusicProvider:
    def __init__(self):
        self.name = "apple"
    
    def validate_url(self, url: str) -> bool:
        """Check if URL is valid Apple Music content"""
        return bool(re.match(
            r"https://music\.apple\.com/.+/(album|song|playlist|music-video|artist)/.+", 
            url
        ))
    
    def extract_content_id(self, url: str) -> str:
        """Extract Apple Music content ID from URL"""
        match = re.search(r'/(album|song|playlist|music-video|artist)/[^/]+/(\d+)', url)
        return match.group(2) if match else "unknown"
    
    async def process(self, url: str, user: dict, options: dict = None) -> dict:
        """Process Apple Music URL with options"""
        # Create user-specific directory
        user_dir = os.path.join(Config.LOCAL_STORAGE, str(user['user_id']), "Apple Music")
        os.makedirs(user_dir, exist_ok=True)
        LOGGER.info(f"Created Apple Music directory: {user_dir}")
        
        # Process options
        cmd_options = self.build_options(options)
        
        # Update user message
        await edit_message(user['bot_msg'], "⏳ Starting Apple Music download...")
        
        # Download content
        result = await run_apple_downloader(url, user_dir, cmd_options, user)
        if not result['success']:
            LOGGER.error(f"Apple downloader failed: {result['error']}")
            return result
        
        # Find downloaded files
        files = []
        for root, _, filenames in os.walk(user_dir):
            for file in filenames:
                file_path = os.path.join(root, file)
                # Collect all relevant files
                if file.endswith(('.m4a', '.flac', '.alac', '.mp4', '.m4v', '.mov')):
                    files.append(file_path)
        
        if not files:
            LOGGER.error(f"No files found in: {user_dir}")
            try:
                LOGGER.error(f"Directory contents: {os.listdir(user_dir)}")
            except Exception as e:
                LOGGER.error(f"Error listing contents: {str(e)}")
            return {'success': False, 'error': "No files downloaded"}
        
        LOGGER.info(f"Found {len(files)} files in {user_dir}")
        
        # Extract metadata - RUN IN THREAD POOL
        items = []
        for file_path in files:
            try:
                # Run synchronous function in thread
                metadata = await asyncio.to_thread(extract_apple_metadata, file_path)
                metadata['filepath'] = file_path
                metadata['provider'] = self.name
                items.append(metadata)
                LOGGER.info(f"Processed file: {file_path}")
            except Exception as e:
                LOGGER.error(f"Metadata extraction failed for {file_path}: {str(e)}")
                # Create default metadata as fallback
                default = default_metadata(file_path)
                default['provider'] = self.name
                items.append(default)
        
        # Handle case where no metadata was extracted
        if not items:
            LOGGER.error("No valid metadata extracted for any files")
            return {'success': False, 'error': "Metadata extraction failed"}
        
        # Determine content type based on file types
        has_video = any(f.endswith(('.mp4', '.m4v', '.mov')) for f in files)
        has_audio = any(f.endswith(('.m4a', '.flac', '.alac')) for f in files)
        is_single = len(items) == 1
        
        if is_single:
            if has_video:
                content_type = 'video'
                folder_path = os.path.dirname(items[0]['filepath'])
            else:
                content_type = 'track'
                folder_path = os.path.dirname(items[0]['filepath'])
        elif has_video and has_audio:
            # Mixed content - treat as playlist
            content_type = 'playlist'
            folder_path = os.path.dirname(os.path.commonpath([i['filepath'] for i in items]))
            LOGGER.warning(f"Mixed video/audio content detected. Treating as playlist: {folder_path}")
        else:
            # Pure audio collection
            content_type = 'album'
            folder_path = os.path.dirname(os.path.commonpath([i['filepath'] for i in items]))
        
        # Record download in history
        content_id = self.extract_content_id(url)
        quality = options.get('mv-max', Config.APPLE_ATMOS_QUALITY) if has_video else \
                 options.get('alac-max', Config.APPLE_ALAC_QUALITY) if 'alac' in (options or {}) else \
                 options.get('atmos-max', Config.APPLE_ATMOS_QUALITY)
        
        # Use first item's title if album title is missing
        album_title = items[0].get('album', items[0]['title'])
        
        download_history.record_download(
            user_id=user['user_id'],
            provider=self.name,
            content_type=content_type,
            content_id=content_id,
            title=album_title,
            artist=items[0]['artist'],
            quality=str(quality)  # Convert to string
        )
        
        return {
            'success': True,
            'type': content_type,
            'items': items,
            'folderpath': folder_path,
            'title': album_title,
            'artist': items[0]['artist'],
            'poster_msg': user['bot_msg']
        }
    
    def build_options(self, options: dict) -> list:
        """Convert options dictionary to command-line flags"""
        if not options:
            return []
        
        cmd_options = []
        option_map = {
            'aac': '--aac',
            'aac-type': '--aac-type',
            'alac-max': '--alac-max',
            'all-album': '--all-album',
            'atmos': '--atmos',
            'atmos-max': '--atmos-max',
            'debug': '--debug',
            'mv-audio-type': '--mv-audio-type',
            'mv-max': '--mv-max',
            'select': '--select',
            'song': '--song'
        }
        
        for key, value in options.items():
            if key in option_map:
                if value is True:  # Flag option
                    cmd_options.append(option_map[key])
                else:  # Value option
                    cmd_options.extend([option_map[key], str(value)])
        
        return cmd_options

async def start_apple(link: str, user: dict, options: dict = None):
    """Handle Apple Music download request with options"""
    try:
        provider = AppleMusicProvider()
        if not provider.validate_url(link):
            await edit_message(user['bot_msg'], "❌ Invalid Apple Music URL")
            return
        
        # Process content with options
        result = await provider.process(link, user, options)
        if not result['success']:
            await edit_message(user['bot_msg'], f"❌ Error: {result['error']}")
            return
        
        # Lazy import to break circular dependency
        from bot.helpers.uploader import (
            track_upload, 
            album_upload, 
            music_video_upload, 
            artist_upload, 
            playlist_upload
        )
        
        # Process and upload content based on type
        if result['type'] == 'track':
            await track_upload(result['items'][0], user)
        elif result['type'] == 'video':
            await music_video_upload(result['items'][0], user)
        elif result['type'] == 'album':
            await album_upload(result, user)
        elif result['type'] == 'playlist':
            await playlist_upload(result, user)
        else:
            await edit_message(user['bot_msg'], f"❌ Unsupported content type: {result['type']}")
            return
        
        # Final cleanup
        await cleanup(user)
        await edit_message(user['bot_msg'], "✅ Apple Music download completed!")
        
    except Exception as e:
        logger.error(f"Apple Music error: {str(e)}", exc_info=True)
        await edit_message(user['bot_msg'], f"❌ Error: {str(e)}")
        await cleanup(user)
