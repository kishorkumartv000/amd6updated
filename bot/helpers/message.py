import os
import sys
import asyncio
import re

# Add helpers directory to sys.path for proper import resolution
helpers_dir = os.path.dirname(os.path.abspath(__file__))
if helpers_dir not in sys.path:
    sys.path.insert(0, helpers_dir)

from pyrogram.types import Message
from pyrogram.errors import MessageNotModified, FloodWait

# Import via bot package instead of direct file reference
from bot import tgclient
from bot.settings import bot_set
from bot.logger import LOGGER

import bot.helpers.translations as lang

current_user = []

user_details = {
    'user_id': None,
    'name': None,
    'user_name': None,
    'r_id': None,
    'chat_id': None,
    'provider': None,
    'bot_msg': None,
    'link': None,
    'override' : None
}


async def fetch_user_details(msg: Message, reply=False) -> dict:
    details = user_details.copy()
    details['user_id'] = msg.from_user.id
    details['name'] = msg.from_user.first_name
    details['user_name'] = msg.from_user.username or msg.from_user.mention()
    details['r_id'] = msg.reply_to_message.id if reply else msg.id
    details['chat_id'] = msg.chat.id
    try:
        details['bot_msg'] = msg.id
    except:
        pass
    return details


async def check_user(uid=None, msg=None, restricted=False) -> bool:
    if restricted:
        if uid in bot_set.admins:
            return True
    else:
        if bot_set.bot_public:
            return True
        else:
            all_chats = list(bot_set.admins) + bot_set.auth_chats + bot_set.auth_users 
            if msg.from_user.id in all_chats:
                return True
            elif msg.chat.id in all_chats:
                return True
    return False


async def antiSpam(uid=None, cid=None, revoke=False) -> bool:
    if revoke:
        if bot_set.anti_spam == 'CHAT+':
            if cid in current_user:
                current_user.remove(cid)
        elif bot_set.anti_spam == 'USER':
            if uid in current_user:
                current_user.remove(uid)
    else:
        if bot_set.anti_spam == 'CHAT+':
            if cid in current_user:
                return True
            else:
                current_user.append(cid)
        elif bot_set.anti_spam == 'USER':
            if uid in current_user:
                return True
            else:
                current_user.append(uid)
        return False


async def send_message(user, item, itype='text', caption=None, markup=None, chat_id=None, meta=None):
    if not isinstance(user, dict):
        user = await fetch_user_details(user)
    chat_id = chat_id if chat_id else user['chat_id']
    
    try:
        if itype == 'text':
            msg = await tgclient.aio.send_message(
                chat_id=chat_id,
                text=item,
                reply_to_message_id=user['r_id'],
                reply_markup=markup,
                disable_web_page_preview=True
            )
        elif itype == 'doc':
            msg = await tgclient.aio.send_document(
                chat_id=chat_id,
                document=item,
                caption=caption,
                reply_to_message_id=user['r_id']
            )
        elif itype == 'audio':
            # SAFE METADATA ACCESS WITH DEFAULTS
            duration = int(meta.get('duration', 0)) if meta else 0
            artist = meta.get('artist', 'Unknown Artist') if meta else 'Unknown Artist'
            title = meta.get('title', 'Unknown Track') if meta else 'Unknown Track'
            thumbnail = meta.get('thumbnail') if meta else None
            
            msg = await tgclient.aio.send_audio(
                chat_id=chat_id,
                audio=item,
                caption=caption,
                duration=duration,
                performer=artist,
                title=title,
                thumb=thumbnail,
                reply_to_message_id=user['r_id']
            )
        elif itype == 'video':  # Added video type support
            # SAFE METADATA ACCESS WITH DEFAULTS
            duration = int(meta.get('duration', 0)) if meta else 0
            width = int(meta.get('width', 1920)) if meta else 1920
            height = int(meta.get('height', 1080)) if meta else 1080
            thumbnail = meta.get('thumbnail') if meta else None
            
            msg = await tgclient.aio.send_video(
                chat_id=chat_id,
                video=item,
                caption=caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumbnail,
                reply_to_message_id=user['r_id']
            )
        elif itype == 'pic':
            msg = await tgclient.aio.send_photo(
                chat_id=chat_id,
                photo=item,
                caption=caption,
                reply_to_message_id=user['r_id']
            )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_message(user, item, itype, caption, markup, chat_id, meta)
    except Exception as e:
        LOGGER.error(f"Error sending message: {str(e)}")
    
    return msg


async def edit_message(msg:Message, text, markup=None, antiflood=True):
    try:
        edited = await tgclient.aio.edit_message_text(
            chat_id=msg.chat.id,
            message_id=msg.id,
            text=text,
            reply_markup=markup,
            disable_web_page_preview=True
        )
        return edited
    except MessageNotModified:
        return None
    except FloodWait as e:
        if antiflood:
            await asyncio.sleep(e.value)
            return await edit_message(msg, text, markup, antiflood)
        else:
            return None
