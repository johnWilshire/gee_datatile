import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

GEE_SERVICE_ACCOUNT = os.getenv("GEE_SERVICE_ACCOUNT", "")
GEE_KEY_FILE = os.getenv("GEE_KEY_FILE", "")
GEE_PROJECT = os.getenv("GEE_PROJECT", "")
GEE_OPT_URL = os.getenv(
    "GEE_OPT_URL", "https://earthengine-highvolume.googleapis.com"
)

# Tile settings
TILE_SIZE = int(os.getenv("TILE_SIZE", "256"))
