import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
OWNER_ID: int = int(os.environ["OWNER_ID"])
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")
DB_PATH: str = os.getenv("DB_PATH", "jakarta_cafe.db")
CAFE_LAT: float = float(os.getenv("CAFE_LAT", "10.62959403416478"))
CAFE_LON: float = float(os.getenv("CAFE_LON", "103.52617840379959"))
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "http://localhost:8082")
PORT: int = int(os.getenv("PORT", "8080"))
SECRET_KEY: str = os.getenv("SECRET_KEY", BOT_TOKEN)

from pathlib import Path
BASE_DIR = Path(__file__).parent
ABA_QR_IMAGE_PATH: str = str(BASE_DIR / "webapp" / "aba-mat-baru.jpg")
