#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import signal
import subprocess

# Set up paths
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    [task.cancel() for task in tasks]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Close all client sessions
    from bot.settings import bot_set
    if bot_set.qobuz:
        await bot_set.qobuz.session.close()
    if bot_set.deezer:
        await bot_set.deezer.session.close()
    if bot_set.tidal:
        await bot_set.tidal.session.close()
    
    loop.stop()

async def main():
    """Main entry point for the bot"""
    from bot import tgclient, settings
    from config import Config
    from pyrogram import idle
    
    # Initialize bot settings
    bot_set = settings.bot_set
    
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, loop))
    
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
    await idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Critical error: {str(e)}")
