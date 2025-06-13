from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS", "service_account.json")
OWNER_EMAIL = os.getenv("OWNER_EMAIL")
USER_CONFIG_FILE = "user_config.json"
