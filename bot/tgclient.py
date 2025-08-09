from pyrogram import Client
from config import Config
from bot import plugins  # Import plugins from bot package

class Bot(Client):
    def __init__(self):
        super().__init__(
            "Apple-Music-Bot",
            api_id=Config.APP_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.TG_BOT_TOKEN,
            plugins=plugins,  # Use the imported plugins
            workdir=Config.WORK_DIR,
            workers=Config.MAX_WORKERS
        )

# Create client instance
aio = Bot()
