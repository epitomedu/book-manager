# db.py
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_books():
    try:
        res = supabase.table("books").select("*").execute()
        return {str(item["barcode"]): item for item in (res.data or [])}
    except Exception as e:
        print(f"[도서 캐시 로드 실패] {e}")
        return {}


def fetch_current_loans():
    try:
        res = (
            supabase.table("current_loans")
            .select("barcode, title, student_name, borrow_date")
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[대출 상태 로드 실패] {e}")
        return []


def fetch_logs():
    try:
        res = supabase.table("logs").select("*").execute()
        return res.data or []
    except Exception as e:
        print(f"[로그 로드 실패] {e}")
        return []


def fetch_logs_ordered():
    try:
        res = (
            supabase.table("logs")
            .select("*")
            .order("date", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[로그 정렬 로드 실패] {e}")
        return []


def fetch_logs_for_migration():
    """마이그레이션 전용: 날짜 오름차순 정렬로 상태 복원 정확도 확보"""
    try:
        res = (
            supabase.table("logs")
            .select("*")
            .order("date", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[마이그레이션 로그 로드 실패] {e}")
        return []


def check_current_loans_exist():
    try:
        return supabase.table("current_loans").select("barcode").limit(1).execute()
    except Exception as e:
        print(f"[대출 테이블 체크 실패] {e}")
        return None


def upsert_current_loans(items):
    try:
        supabase.table("current_loans").upsert(items).execute()
    except Exception as e:
        print(f"[대출 마이그레이션 실패] {e}")


def insert_log(log_data):
    supabase.table("logs").insert(log_data).execute()


def insert_current_loan(loan_data):
    supabase.table("current_loans").insert(loan_data).execute()


def delete_current_loan(barcode):
    supabase.table("current_loans").delete().eq("barcode", barcode).execute()


def upsert_books(records):
    supabase.table("books").upsert(records).execute()


def delete_book_by_barcode(barcode):
    supabase.table("books").delete().eq("barcode", barcode).execute()
