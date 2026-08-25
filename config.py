# config.py
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "260608")

MAX_LOAN = 4
OVERDUE_MINUTES = 1          # 테스트용 (분). 실사용 시 일 단위로 변경 권장
POLL_INTERVAL_MS = 5000
MIGRATED_MARKER = "_MIGRATED_CHECK_"
