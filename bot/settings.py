import os
import sys
import json
import base64
import requests
import subprocess

# Add bot directory to sys.path for proper import resolution
bot_dir = os.path.dirname(os.path.abspath(__file__))
if bot_dir not in sys.path:
    sys.path.insert(0, bot_dir)

import bot.helpers.translations as lang
from config import Config
from bot.logger import LOGGER

from .helpers.database.pg_impl import set_db, download_history
from .helpers.qobuz.qopy import qobuz_api
from .helpers.deezer.dzapi import deezerapi
from .helpers.tidal.tidal_api import tidalapi
from .helpers.translations import lang_available


# Helper functions
def __getvalue__(var):
    value, _ = set_db.get_variable(var)
    return value if value else False

def __encrypt_string__(string):
    s = bytes(string, 'utf-8')
    s = base64.b64encode(s)
    return s

def __decrypt_string__(string):
    try:
        s = base64.b64decode(string)
        s = s.decode()
        return s
    except:
        return string

class BotSettings:
    def __init__(self):
        self.deezer = False
        self.qobuz = False
        # Add this line to initialize can_enable_tidal
        self.can_enable_tidal = Config.ENABLE_TIDAL and Config.ENABLE_TIDAL.lower() == "true"
        self.admins = Config.ADMINS
        self.apple = None  # Apple Music settings placeholder

        self.set_language()

        db_users, _ = set_db.get_variable('AUTH_USERS')
        self.auth_users = json.loads(db_users) if db_users else []
        db_chats, _ = set_db.get_variable('AUTH_CHATS')
        self.auth_chats = json.loads(db_chats) if db_chats else []

        self.rclone = False
        self.check_upload_mode()
        self.initialize_apple()

        spam, _ = set_db.get_variable('ANTI_SPAM')
        self.anti_spam = spam if spam else 'OFF'

        self.bot_public = __getvalue__('BOT_PUBLIC')
        self.art_poster = __getvalue__('ART_POSTER')
        self.playlist_sort = __getvalue__('PLAYLIST_SORT')
        self.disable_sort_link = __getvalue__('PLAYLIST_LINK_DISABLE')
        self.artist_batch = __getvalue__('ARTIST_BATCH_UPLOAD')
        self.playlist_conc = __getvalue__('PLAYLIST_CONCURRENT')
        
        link_option, _ = set_db.get_variable('RCLONE_LINK_OPTIONS')
        self.link_options = link_option if self.rclone and link_option else 'False'

        self.album_zip = __getvalue__('ALBUM_ZIP')
        self.playlist_zip = __getvalue__('PLAYLIST_ZIP')
        self.artist_zip = __getvalue__('ARTIST_ZIP')

        self.clients = []
        self.download_history = download_history

    def check_upload_mode(self):
        """Determine upload mode based on configuration"""
        if os.path.exists('rclone.conf'):
            self.rclone = True
        elif Config.RCLONE_CONFIG:
            if Config.RCLONE_CONFIG.startswith('http'):
                try:
                    rclone = requests.get(Config.RCLONE_CONFIG, allow_redirects=True)
                    if rclone.status_code == 200:
                        with open('rclone.conf', 'wb') as f:
                            f.write(rclone.content)
                        self.rclone = True
                    else:
                        LOGGER.error(f"Rclone config download failed: HTTP {rclone.status_code}")
                except Exception as e:
                    LOGGER.error(f"Rclone config download error: {str(e)}")
            else:
                if os.path.exists(Config.RCLONE_CONFIG):
                    self.rclone = True
        
        db_upload, _ = set_db.get_variable('UPLOAD_MODE')
        if self.rclone and db_upload == 'RCLONE':
            self.upload_mode = 'RCLONE'
        elif db_upload == 'Telegram' or db_upload == 'Local':
            self.upload_mode = db_upload
        else:
            self.upload_mode = 'Local'

    def initialize_apple(self):
        """Initialize Apple Music settings"""
        self.apple = {
            'downloader_path': Config.DOWNLOADER_PATH,
            'installer_path': Config.INSTALLER_PATH,
            'format': __getvalue__('APPLE_DEFAULT_FORMAT') or Config.APPLE_DEFAULT_FORMAT,
            'alac_quality': int(__getvalue__('APPLE_ALAC_QUALITY') or Config.APPLE_ALAC_QUALITY),
            'atmos_quality': int(__getvalue__('APPLE_ATMOS_QUALITY') or Config.APPLE_ATMOS_QUALITY)
        }
        
        # Ensure downloader is installed
        if not os.path.exists(Config.DOWNLOADER_PATH):
            LOGGER.warning("Apple Music downloader not found! Attempting installation...")
            try:
                subprocess.run([Config.INSTALLER_PATH], check=True)
                LOGGER.info("Apple Music downloader installed successfully")
            except Exception as e:
                LOGGER.error(f"Apple Music installer failed: {str(e)}")

    async def login_qobuz(self):
        """Initialize Qobuz client"""
        if Config.QOBUZ_EMAIL or Config.QOBUZ_USER:
            try:
                await qobuz_api.login()
                self.qobuz = qobuz_api
                self.clients.append(qobuz_api)
                quality, _ = set_db.get_variable("QOBUZ_QUALITY")
                if quality:
                    qobuz_api.quality = int(quality)
            except Exception as e:
                LOGGER.error(f"Qobuz login failed: {str(e)}")

    async def login_deezer(self):
        """Initialize Deezer client"""
        if Config.DEEZER_ARL or Config.DEEZER_EMAIL:
            if Config.DEEZER_BF_SECRET:
                login = await deezerapi.login()
                if login:
                    self.deezer = deezerapi
                    self.clients.append(deezerapi)
                    LOGGER.info(f"DEEZER : Subscription - {deezerapi.user['OFFER_NAME']}")
                else:
                    try:
                        await deezerapi.session.close()
                    except:
                        pass
            else:
                LOGGER.error('DEEZER : Check BF_SECRET and TRACK_URL_KEY')

    async def login_tidal(self):
        """Initialize Tidal client"""
        if not self.can_enable_tidal:
            return

        data = None
        if Config.TIDAL_REFRESH_TOKEN:
            data = {
                'user_id': None, 
                'refresh_token': Config.TIDAL_REFRESH_TOKEN, 
                'country_code': Config.TIDAL_COUNTRY_CODE
            }
        else:
            _, saved_info = set_db.get_variable("TIDAL_AUTH_DATA")
            if saved_info:
                try:
                    data = json.loads(__decrypt_string__(saved_info))
                except Exception as e:
                    LOGGER.error(f"TIDAL: Failed to parse saved auth data: {e}")
                    return

        if not data:
            return

        sub = await tidalapi.login_from_saved(data)
        if sub:
            LOGGER.info(f"TIDAL: Successfully loaded account - {sub}")
        
        if quality := __getvalue__('TIDAL_QUALITY'):
            tidalapi.quality = quality
        
        if spatial := __getvalue__('TIDAL_SPATIAL'):
            tidalapi.spatial = spatial
        
        self.tidal = tidalapi 
        self.clients.append(tidalapi)

    async def save_tidal_login(self, session):
        """Save Tidal login session"""
        data = {
            "user_id": session.user_id,
            "refresh_token": session.refresh_token,
            "country_code": session.country_code
        }
        txt = json.dumps(data)
        set_db.set_variable("TIDAL_AUTH_DATA", 0, True, __encrypt_string__(txt))

    def set_language(self):
        """Set bot language"""
        db_lang, _ = set_db.get_variable('BOT_LANGUAGE')
        self.bot_lang = db_lang if db_lang else 'en'

        for item in lang_available:
            if item.__language__ == self.bot_lang:
                lang.s = item
                break

bot_set = BotSettings()
