import os
import sys
from config import Config

# Add bot directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Get bot username from config
bot_username = Config.BOT_USERNAME

class CMD:
    START = ["start", f"start@{bot_username}"]
    HELP = ["help", f"help@{bot_username}"]
    SETTINGS = ["settings", f"settings@{bot_username}"]
    DOWNLOAD = ["download", f"download@{bot_username}"]
    BAN = ["ban", f"ban@{bot_username}"]
    AUTH = ["auth", f"auth@{bot_username}"]
    LOG = ["log", f"log@{bot_username}"]

cmd = CMD()

# Define plugins for Pyrogram
plugins = {
    "root": "bot.modules"
}
