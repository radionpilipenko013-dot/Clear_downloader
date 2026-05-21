from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TOKEN")
BOT_TOKEN = TOKEN  
DB_URL = "sqlite+aiosqlite:///database.db"
DOWNLOADS_DIR = "downloads"
ADMIN_ID = 5253335910