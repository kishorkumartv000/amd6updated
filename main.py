#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import subprocess  # Add missing import

# Set up paths
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main entry point for the bot"""
    from bot import tgclient, settings
    from config import Config
    from pyrogram import idle  # Import idle from pyrogram
    
    # Initialize bot settings
    bot_set = settings.bot_set
    
    # Ensure download directory exists
    if not os.path.isdir(Config.LOCAL_STORAGE):
        os.makedirs(Config.LOCAL_STORAGE)
        logger.info(f"Created download directory: {Config.LOCAL_STORAGE}")
    
    # Initialize Apple Music downloader
    if not os.path.exists(Config.DOWNLOADER_PATH):
        logger.warning("Apple Music downloader not found! Attempting installation...")
        try:
            subprocess.run([Config.INSTALLER_PATH], check=True)
            logger.info("Apple Music downloader installed successfully")
        except Exception as e:
            logger.error(f"Apple Music installer failed: {str(e)}")
    
    # Set execute permissions
    if os.path.exists(Config.DOWNLOADER_PATH):
        try:
            os.chmod(Config.DOWNLOADER_PATH, 0o755)
            logger.info(f"Set execute permissions on: {Config.DOWNLOADER_PATH}")
        except Exception as e:
            logger.error(f"Failed to set permissions: {str(e)}")
    
    # Initialize providers
    await bot_set.login_qobuz()
    await bot_set.login_deezer()
    await bot_set.login_tidal()
    
    # Start the bot
    logger.info("Starting Apple Music Downloader Bot...")
    await tgclient.aio.start()
    await idle()  # Use the imported idle function

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Critical error: {str(e)}")
