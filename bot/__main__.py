import os
import subprocess
from config import Config
from .logger import LOGGER
from .tgclient import aio

def start_bot():
    """Initialize bot components"""
    # Ensure download directory exists
    if not os.path.isdir(Config.LOCAL_STORAGE):
        os.makedirs(Config.LOCAL_STORAGE)
        LOGGER.info(f"Created download directory: {Config.LOCAL_STORAGE}")
    
    # Initialize Apple Music downloader
    if not os.path.exists(Config.DOWNLOADER_PATH):
        LOGGER.warning("Apple Music downloader not found! Attempting installation...")
        try:
            subprocess.run([Config.INSTALLER_PATH], check=True)
            LOGGER.info("Apple Music downloader installed successfully")
        except Exception as e:
            LOGGER.error(f"Apple Music installer failed: {str(e)}")
    
    # Set execute permissions
    if os.path.exists(Config.DOWNLOADER_PATH):
        try:
            os.chmod(Config.DOWNLOADER_PATH, 0o755)
            LOGGER.info(f"Set execute permissions on: {Config.DOWNLOADER_PATH}")
        except Exception as e:
            LOGGER.error(f"Failed to set permissions: {str(e)}")
    
    LOGGER.info("Apple Music Downloader Bot initialized")
