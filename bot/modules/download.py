from pyrogram.types import Message
from pyrogram import Client, filters

# Import CMD from bot package
from bot import cmd as CMD

from bot.logger import LOGGER
import bot.helpers.translations as lang

# Fixed imports using relative paths
from ..helpers.utils import cleanup
from ..helpers.qobuz.handler import start_qobuz
from ..helpers.tidal.handler import start_tidal
from ..helpers.deezer.handler import start_deezer
from ..providers.apple import start_apple
from ..helpers.message import send_message, antiSpam, check_user, fetch_user_details, edit_message


@Client.on_message(filters.command(CMD.DOWNLOAD))
async def download_track(c, msg: Message):
    if await check_user(msg=msg):
        try:
            if msg.reply_to_message:
                # Get options from message text and URL from reply
                parts = msg.text.split()
                options = parse_options(parts[1:]) if len(parts) > 1 else {}
                link = msg.reply_to_message.text
                reply = True
            else:
                # Parse options and URL from message text
                parts = msg.text.split()[1:]
                options = parse_options(parts)
                # Last part is URL
                link = parts[-1] if parts else None
                reply = False
        except Exception as e:
            LOGGER.error(f"Error parsing command: {e}")
            return await send_message(msg, lang.s.ERR_NO_LINK)

        if not link:
            return await send_message(msg, lang.s.ERR_LINK_RECOGNITION)
        
        spam = await antiSpam(msg.from_user.id, msg.chat.id)
        if not spam:
            user = await fetch_user_details(msg, reply)
            user['link'] = link
            user['bot_msg'] = await send_message(msg, 'Starting download...')
            try:
                await start_link(link, user, options)
                await send_message(user, lang.s.TASK_COMPLETED)
            except Exception as e:
                LOGGER.error(f"Download failed: {e}")
                # USE SAFE ERROR MESSAGING
                error_msg = f"Download failed: {str(e)}"
                await send_message(user, error_msg)
            await c.delete_messages(msg.chat.id, user['bot_msg'].id)
            await cleanup(user)  # deletes uploaded files
            await antiSpam(msg.from_user.id, msg.chat.id, True)


def parse_options(parts: list) -> dict:
    """Parse command-line options from message parts"""
    options = {}
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('--'):
            key = part[2:]
            # Check if next part is a value
            if i + 1 < len(parts) and not parts[i+1].startswith('--'):
                options[key] = parts[i+1]
                i += 1
            else:
                options[key] = True
        i += 1
    return options


async def start_link(link: str, user: dict, options: dict = None):
    """
    Route download request to appropriate provider handler
    """
    tidal = ["https://tidal.com", "https://listen.tidal.com", "tidal.com", "listen.tidal.com"]
    deezer = ["https://link.deezer.com", "https://deezer.com", "deezer.com", "https://www.deezer.com", "link.deezer.com"]
    qobuz = ["https://play.qobuz.com", "https://open.qobuz.com", "https://www.qobuz.com"]
    spotify = ["https://open.spotify.com"]
    apple_music = ["https://music.apple.com"]
    
    if link.startswith(tuple(tidal)):
        await start_tidal(link, user)
    elif link.startswith(tuple(deezer)):
        await start_deezer(link, user)
    elif link.startswith(tuple(qobuz)):
        user['provider'] = 'Qobuz'
        await start_qobuz(link, user)
    elif link.startswith(tuple(spotify)):
        return 'spotify'
    elif link.startswith(tuple(apple_music)):
        user['provider'] = 'Apple'
        await edit_message(user['bot_msg'], "Starting Apple Music download...")
        await start_apple(link, user, options)
    else:
        await send_message(user, lang.s.ERR_UNSUPPORTED_LINK)
        return None
