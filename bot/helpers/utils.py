import os
import math
import aiohttp
import asyncio
import shutil
import zipfile
import re
import json
import base64
import requests
from pathlib import Path
from urllib.parse import quote
from aiohttp import ClientTimeout
from concurrent.futures import ThreadPoolExecutor
from pyrogram.errors import FloodWait

# Import Config for Apple Music settings
from config import Config
import bot.helpers.translations as lang

from ..logger import LOGGER
from ..settings import bot_set
from .buttons.links import links_button

# FIXED: Use absolute imports for message functions
from .message import send_message, edit_message

MAX_SIZE = 1.9 * 1024 * 1024 * 1024  # 2GB

async def download_file(url, path, retries=3, timeout=30):
    """
    Download a file with retry logic and timeout
    Args:
        url (str): URL to download
        path (str): Full path to save the file
        retries (int): Number of retry attempts
        timeout (int): Timeout in seconds
    Returns:
        str or None: Error message if failed, else None
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 4):
                                f.write(chunk)
                        return None
                    else:
                        return f"HTTP Status: {response.status}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retries:
                return f"Failed after {retries} attempts: {str(e)}"
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            return f"Unexpected error: {str(e)}"


async def format_string(text:str, data:dict, user=None):
    """
    Format text using metadata placeholders
    Args:
        text: Template text with placeholders
        data: Metadata dictionary
        user: User details
    Returns:
        Formatted string
    """
    replacements = {
        '{title}': data.get('title', ''),
        '{album}': data.get('album', ''),
        '{artist}': data.get('artist', ''),
        '{albumartist}': data.get('albumartist', ''),
        '{tracknumber}': str(data.get('tracknumber', '')),
        '{date}': str(data.get('date', '')),
        '{upc}': str(data.get('upc', '')),
        '{isrc}': str(data.get('isrc', '')),
        '{totaltracks}': str(data.get('totaltracks', '')),
        '{volume}': str(data.get('volume', '')),
        '{totalvolume}': str(data.get('totalvolume', '')),
        '{extension}': data.get('extension', ''),
        '{duration}': str(data.get('duration', '')),
        '{copyright}': data.get('copyright', ''),
        '{genre}': data.get('genre', ''),
        '{provider}': data.get('provider', '').title(),
        '{quality}': data.get('quality', ''),
        '{explicit}': str(data.get('explicit', '')),
    }
    
    if user:
        replacements['{user}'] = user.get('name', '')
        replacements['{username}'] = user.get('user_name', '')
    
    for key, value in replacements.items():
        text = text.replace(key, value)
        
    return text


async def run_concurrent_tasks(tasks, progress_details=None):
    """
    Run tasks concurrently with progress tracking
    Args:
        tasks: List of async tasks
        progress_details: Progress message details
    Returns:
        Results of all tasks
    """
    semaphore = asyncio.Semaphore(Config.MAX_WORKERS)
    completed = 0
    total = len(tasks)
    
    async def run_task(task):
        nonlocal completed
        async with semaphore:
            result = await task
            completed += 1
            if progress_details:
                progress = int((completed / total) * 100)
                try:
                    await edit_message(
                        progress_details['msg'],
                        f"{progress_details['text']}\nProgress: {progress}%"
                    )
                except FloodWait:
                    pass
            return result
            
    return await asyncio.gather(*(run_task(task) for task in tasks))


async def create_link(path, basepath):
    """
    Create rclone and index links
    Args:
        path: Full file path
        basepath: Base directory path
    Returns:
        rclone_link, index_link
    """
    path = str(Path(path).relative_to(basepath))

    rclone_link = None
    index_link = None

    if bot_set.link_options in ['RCLONE', 'Both']:
        cmd = f'rclone link --config ./rclone.conf "{Config.RCLONE_DEST}/{path}"'
        task = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await task.communicate()

        if task.returncode == 0:
            rclone_link = stdout.decode().strip()
        else:
            error_message = stderr.decode().strip()
            LOGGER.debug(f"Failed to get link: {error_message}")
            
    if bot_set.link_options in ['Index', 'Both']:
        if Config.INDEX_LINK:
            index_link =  Config.INDEX_LINK + '/' + quote(path)

    return rclone_link, index_link


async def zip_handler(folderpath):
    """
    Zip folder based on upload mode
    Args:
        folderpath: Path to folder
    Returns:
        List of zip paths
    """
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        if bot_set.upload_mode == 'Telegram':
            zips = await loop.run_in_executor(pool, split_zip_folder, folderpath)
        else:
            zips = await loop.run_in_executor(pool, zip_folder, folderpath)
        return zips


def split_zip_folder(folderpath) -> list:
    """
    Split large folders into multiple zip files
    Args:
        folderpath: Path to folder
    Returns:
        List of zip file paths
    """
    zip_paths = []
    part_num = 1
    current_size = 0
    current_files = []

    def add_to_zip(zip_name, files_to_add):
        nonlocal part_num
        if part_num == 1:
            zip_path = f"{zip_name}.zip"
        else:
            zip_path = f"{zip_name}.part{part_num}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arcname in files_to_add:
                zipf.write(file_path, arcname)
                os.remove(file_path)  # Delete after zipping
        return zip_path

    for root, dirs, files in os.walk(folderpath):
        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)
            arcname = os.path.relpath(file_path, folderpath)

            # Start new zip if adding would exceed max size
            if current_size + file_size > MAX_SIZE:
                zip_paths.append(add_to_zip(folderpath, current_files))
                part_num += 1
                current_files = []
                current_size = 0

            # Add to current group
            current_files.append((file_path, arcname))
            current_size += file_size

    # Create final zip with remaining files
    if current_files:
        zip_paths.append(add_to_zip(folderpath, current_files))

    return zip_paths


def zip_folder(folderpath) -> str:
    """
    Create single zip of folder
    Args:
        folderpath: Path to folder
    Returns:
        Path to zip file
    """
    zip_path = f"{folderpath}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folderpath):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folderpath))
                os.remove(file_path)
    
    return zip_path


async def move_sorted_playlist(metadata, user) -> str:
    """
    Organize playlist files into folder structure
    Args:
        metadata: Playlist metadata
        user: User details
    Returns:
        Path to playlist folder
    """
    source_folder = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/{metadata['provider']}"
    destination_folder = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/{metadata['provider']}/{metadata['title']}"

    os.makedirs(destination_folder, exist_ok=True)

    # Move all artist/album folders
    folders = [
        os.path.join(source_folder, name) for name in os.listdir(source_folder) 
        if os.path.isdir(os.path.join(source_folder, name))
    ]

    for folder in folders:
        shutil.move(folder, destination_folder)

    return destination_folder


async def post_art_poster(user:dict, meta:dict):
    """
    Post album/playlist art as image
    Args:
        user: User details
        meta: Item metadata
    Returns:
        Message object
    """
    photo = meta['cover']
    if meta['type'] == 'album':
        caption = await format_string(lang.s.ALBUM_TEMPLATE, meta, user)
    else:
        caption = await format_string(lang.s.PLAYLIST_TEMPLATE, meta, user)
    
    if bot_set.art_poster:
        return await send_message(user, photo, 'pic', caption)


async def create_simple_text(meta, user):
    """
    Create simple caption for items
    Args:
        meta: Item metadata
        user: User details
    Returns:
        Formatted caption text
    """
    return await format_string(
        lang.s.SIMPLE_TITLE.format(
            meta['title'],
            meta['type'].title(),
            meta['provider']
        ), 
        meta, 
        user
    )


async def edit_art_poster(metadata, user, r_link, i_link, caption):
    """
    Edit existing art poster with links
    Args:
        metadata: Item metadata
        user: User details
        r_link: Rclone link
        i_link: Index link
        caption: Text to display
    """
    markup = links_button(r_link, i_link)
    await edit_message(
        metadata['poster_msg'],
        caption,
        markup
    )


async def post_simple_message(user, meta, r_link=None, i_link=None):
    """
    Send simple message with optional links
    Args:
        user: User details
        meta: Item metadata
        r_link: Rclone link
        i_link: Index link
    Returns:
        Message object
    """
    caption = await create_simple_text(meta, user)
    markup = links_button(r_link, i_link)
    return await send_message(user, caption, markup=markup)


async def progress_message(done, total, details):
    """
    Update progress message
    Args:
        done: Completed items
        total: Total items
        details: Progress message details
    """
    filled = math.floor((done / total) * 10)
    empty = 10 - filled
    
    progress_bar = "{0}{1}".format(
        ''.join(["▰" for _ in range(filled)]),
        ''.join(["▱" for _ in range(empty)])
    )

    try:
        await edit_message(
            details['msg'],
            details['text'].format(
                progress_bar, 
                done, 
                total, 
                details['title'],
                details['type'].title()
            ),
            None,
            False
        )
    except FloodWait:
        pass  # Skip update during flood limits


async def cleanup(user=None, metadata=None):
    """
    Clean up downloaded files
    Args:
        user: User details (cleans user directory)
        metadata: Item metadata (cleans specific item)
    """
    if metadata:
        try:
            # Apple Music specific cleanup
            if "Apple Music" in metadata.get('folderpath', ''):
                if os.path.exists(metadata['folderpath']):
                    shutil.rmtree(metadata['folderpath'], ignore_errors=True)
                return
            
            # Existing cleanup for other providers
            if metadata['type'] == 'album':
                is_zip = bot_set.album_zip
            elif metadata['type'] == 'artist':
                is_zip = bot_set.artist_zip
            else:
                is_zip = bot_set.playlist_zip
                
            if is_zip:
                paths = metadata['folderpath'] if isinstance(metadata['folderpath'], list) else [metadata['folderpath']]
                for path in paths:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except:
                        pass
            else:
                if os.path.exists(metadata['folderpath']):
                    shutil.rmtree(metadata['folderpath'], ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Metadata cleanup error: {str(e)}")
    
    if user:
        try:
            # Clean up Apple Music directory
            apple_dir = os.path.join(Config.LOCAL_STORAGE, "Apple Music", str(user['user_id']))
            if os.path.exists(apple_dir):
                shutil.rmtree(apple_dir, ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Apple cleanup error: {str(e)}")
        
        try:
            # Clean up old-style directories
            old_dir = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}/"
            if os.path.exists(old_dir):
                shutil.rmtree(old_dir, ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Old dir cleanup error: {str(e)}")
        
        try:
            temp_dir = f"{Config.DOWNLOAD_BASE_DIR}/{user['r_id']}-temp/"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            LOGGER.info(f"Temp dir cleanup error: {str(e)}")
