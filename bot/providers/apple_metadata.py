import os
import mutagen
import re
import time
from mutagen.mp4 import MP4
from pathlib import Path
from bot.logger import LOGGER

def extract_audio_metadata(file_path: str) -> dict:
    """
    Extract metadata from audio files
    Args:
        file_path: Path to audio file
    Returns:
        Metadata dictionary
    """
    try:
        if file_path.endswith('.m4a'):
            audio = MP4(file_path)
            return {
                'title': audio.get('\xa9nam', ['Unknown'])[0],
                'artist': audio.get('\xa9ART', ['Unknown Artist'])[0],
                'album': audio.get('\xa9alb', ['Unknown Album'])[0],
                'duration': int(audio.info.length),
                'thumbnail': extract_cover_art(audio, file_path)
            }
        else:
            # Handle other audio formats like mp3, flac, etc.
            audio = mutagen.File(file_path)
            return {
                'title': audio.get('title', ['Unknown'])[0],
                'artist': audio.get('artist', ['Unknown Artist'])[0],
                'album': audio.get('album', ['Unknown Album'])[0],
                'duration': int(audio.info.length),
                'thumbnail': extract_cover_art(audio, file_path) if hasattr(audio, 'pictures') else None
            }
    except Exception as e:
        LOGGER.error(f"Audio metadata extraction failed: {str(e)}")
        return default_metadata(file_path)

def extract_video_metadata(file_path: str) -> dict:
    """
    Extract metadata from video files
    Args:
        file_path: Path to video file
    Returns:
        Metadata dictionary with video-specific properties
    """
    try:
        if file_path.endswith(('.mp4', '.m4v', '.mov')):
            video = MP4(file_path)
            return {
                'title': video.get('\xa9nam', ['Unknown'])[0],
                'artist': video.get('\xa9ART', ['Unknown Artist'])[0],
                'duration': int(video.info.length),
                'thumbnail': extract_cover_art(video, file_path),
                'width': video.get('width', [1920])[0],
                'height': video.get('height', [1080])[0]
            }
        else:
            return default_metadata(file_path)
    except Exception as e:
        LOGGER.error(f"Video metadata extraction failed: {str(e)}")
        return default_metadata(file_path)

def extract_apple_metadata(file_path: str) -> dict:
    """
    Extract metadata from Apple Music files (audio or video)
    Args:
        file_path: Path to media file
    Returns:
        Metadata dictionary
    """
    try:
        if file_path.endswith('.m4a'):
            return extract_audio_metadata(file_path)
        elif file_path.endswith(('.mp4', '.m4v', '.mov')):
            return extract_video_metadata(file_path)
        else:
            # Handle other file types with mutagen
            audio = mutagen.File(file_path)
            return {
                'title': audio.get('title', ['Unknown'])[0],
                'artist': audio.get('artist', ['Unknown Artist'])[0],
                'album': audio.get('album', ['Unknown Album'])[0],
                'duration': int(audio.info.length),
                'thumbnail': extract_cover_art(audio, file_path) if hasattr(audio, 'pictures') else None
            }
    except Exception as e:
        LOGGER.error(f"Apple metadata extraction failed: {str(e)}")
        return default_metadata(file_path)

def extract_cover_art(media, file_path):
    """
    Extract cover art from audio/video file
    Args:
        media: Mutagen file object
        file_path: Path to media file
    Returns:
        Path to extracted cover art or None
    """
    try:
        # Handle MP4 cover art
        if 'covr' in media:
            cover_data = media['covr'][0]
            cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
            with open(cover_path, 'wb') as f:
                f.write(cover_data)
            return cover_path
        
        # Handle ID3 tags (MP3)
        elif hasattr(media, 'pictures') and media.pictures:
            cover_data = media.pictures[0].data
            cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
            with open(cover_path, 'wb') as f:
                f.write(cover_data)
            return cover_path
        
        # Handle FLAC/Vorbis comments
        elif 'metadata_block_picture' in media:
            for block in media.get('metadata_block_picture', []):
                try:
                    data = base64.b64decode(block)
                    pic = mutagen.flac.Picture(data)
                    if pic.type == 3:  # Front cover
                        cover_path = f"{os.path.splitext(file_path)[0]}.jpg"
                        with open(cover_path, 'wb') as f:
                            f.write(pic.data)
                        return cover_path
                except:
                    continue
    except Exception as e:
        LOGGER.error(f"Failed to extract cover art: {str(e)}")
    return None

def default_metadata(file_path):
    """Return default metadata when extraction fails"""
    return {
        'title': os.path.splitext(os.path.basename(file_path))[0],
        'artist': 'Unknown Artist',
        'album': 'Unknown Album',
        'duration': 0,
        'thumbnail': None
    }
