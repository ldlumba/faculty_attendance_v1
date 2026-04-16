import os
from dotenv import load_dotenv

load_dotenv()


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


SUPABASE_URL = require_env("SUPABASE_URL")
SUPABASE_KEY = require_env("SUPABASE_KEY")
SECRET_KEY = require_env("SECRET_KEY")
ADMIN_PASSWORD = require_env("ADMIN_PASSWORD")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Manila")
