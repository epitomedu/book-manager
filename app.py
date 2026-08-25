import sys
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QHeaderView, QMessageBox,
    QTabWidget, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QIntValidator
from supabase import create_client

# ==========================================
# Supabase 설정
# ==========================================
SUPABASE_URL = "https://ldpbwvdpltpdjazqviwa.supabase.co"
SUPABASE_KEY = "sb_publishable_nXwWJyL3ZzBN_nfTuQbieA_NqVkkJ6n"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 운영 설정
# ==========================================
MAX_LOAN = 4
OVERDUE_MINUTES = 1       # ★ 테스트용 연체 기준 (1분)
# OVERDUE_DAYS = 7        # 정식 운영 시 이걸로 바꾸고 관련 계산도 일 단위로 변경
POLL_INTERVAL_MS = 5000   # 5초마다 자동 동기화


class KoreanLineEdit(QLineEdit):
    """한글 조합 중복 입력 방지"""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self._composing = False

    def inputMethodEvent(self, event):
        if event.preeditString():
            self._composing = True
        if event.commitString():
            self._composing = False
        super().inputMethodEvent(event)
        if not event.preeditString():
            self._composing = False

    def isComposing(self):
        return self._composing

    def focusOutEvent(self, event):
        self._composing = False
        super().focusOutEvent(event)


class LibraryApp(QWidget):
    def __init__(self):
        super().__init__()
        self.books_cache = {}
        self.loan_status = {}
        self.current_book = None

        self.init_ui()
        self.full_sync()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.background_sync)
        self.poll_timer.start(POLL_INTERVAL_MS)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start(1000)

    def full_sync(self):
        self.load_books_cache()
        self.rebuild_loan_status()
        self.update_status_bar()

    def background_sync(self):
        try:
            self.load_books_cache()
            self.rebuild_loan_status()
            self.update_status_bar()
        except Exception as e:
            print(f"[폴링 오류] {e}")

    def manual_refresh(self):
        self.btn_refresh.setEnabled(False)
        try:
            self.full_sync()
            self.lbl_status.setText(f"[알림] 새로고침 완료 ({datetime.now().strftime('%H:%M:%S')})")
            self.lbl_status.setStyleSheet("color: #63b3ed; font-weight: bold;")
        except Exception as e:
            self.lbl_status.setText(f"[오류] {e}")
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
        finally:
            self.btn_refresh.setEnabled(True)

    def load_books_cache(self):
        try:
            res = supabase.table("books").select("*").execute()
            self.books_cache = {str(item["barcode"]): item for item in (res.data or [])}
        except Exception as e:
            print(f"[도서 캐시 오류] {e}")

    def rebuild_loan_status(self):
        try:
            res = (
                supabase.table("logs")
                .select("barcode, action, student_name, date, title")
                .order("date")
                .execute()
            )
            status = {}
            for log in (res.data or []):
                bc = str(log.get("barcode", ""))
                action = log.get("action")
                name = log.get("student_name", "")
                title = log.get("title", "")
                date_str = log.get("date", "")

                try:
                    loan_date = datetime.fromisoformat(
                        str(date_str).replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except:
                    loan_date = datetime.now()

                if action == "RENT":
                    status[bc] = {"name": name, "date": loan_date, "title": title}
                elif action == "RETURN" and bc in status:
                    del status[bc]

            self.loan_status = status
        except Exception as e:
            print(f"[대출 상태 계산 오류] {e}")

    def get_student_id(self):
        name = self.entry_student.text().strip()
        phone = self.entry_phone.text().strip()
        if not name or not phone:
            return None
        return f"{name} ({phone})"

    def get_student_loan_count(self, student_id):
        return sum(1 for v in self.loan_status.values() if v["name"] == student_id)

    def get_overdue_count(self):
        now = datetime.now()
        return sum(
            1 for v in self.loan_status.values()
            if (now - v["date"]).total_seconds() / 60 > OVERDUE_MINUTES
        )

    def force_commit_ime(self):
        focused = QApplication.focusWidget()
        if focused and isinstance(focused, KoreanLineEdit):
            focused.clearFocus()
            QApplication.processEvents()
            focused.setFocus()
            QApplication.processEvents()

    def update_status_bar(self):
        total = len(self.loan_status)
        overdue = self.get_overdue_count()
        self.lbl_bottom.setText(
            f"📚 대출 중: {total}권   |   ⚠️ 연체: {overdue}권   |   최대 {MAX_LOAN}권/인   |   테스트 1분 연체"
        )
        if overdue > 0:
            self.lbl_bottom.setStyleSheet(
                "background:#742a2a; color:#fed7d7; font-weight:bold; font-size:13px; padding:10px; border-radius:6px;"
            )
        else:
            self.lbl_bottom.setStyleSheet(
                "background:#2d3748; color:#a0aec0; font-weight:bold; font-size:13px; padding:10px; border-radius:6px;"
            )

    def init_ui(self):
        self.setWindowTitle("📚 Epitome Edu Library System (테스트 - 1분 연체)")
        self.resize(600, 780)
        self.setStyleSheet("""
            QWidget { background:#1a202c; color:#e2e8f0; font-family:'맑은 고딕','Apple SD Gothic Neo',sans-serif; }
            QLineEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:6px; padding:8px; font-size:14px; }
            QPushButton { background:#3182ce; color:white; border-radius:6px; font-weight:bold; font-size:13px; padding:10px; }
            QPushButton:hover { background:#2b6cb0; }
            QLabel { font-size:13px; }
            QTabWidget::pane { border:1px solid #4a5568; border-radius:8px; }
            QTabBar::tab { background:#2d3748; color:#a0aec0; padding:10px 16px; margin-right:4px;
                           border-top-left-radius:8px; border-top-right-radius:8px; font-weight:bold; }
            QTabBar::tab:selected { background:#3182ce; color:white; }
            QGroupBox { border:1px solid #4a5568; border-radius:8px; margin-top:12px; font-weight:bold; color:#90cdf4; padding-top:10px; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; }
        """)

        main = QVBoxLayout(self)
        main.setSpacing(12)
        main.setContentsMargins(14, 14, 14, 14)

        top = QHBoxLayout()
        title = QLabel("📚 라이브러리 관리 시스템 (테스트 1분 연체)")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#63b3ed;")
        top.addWidget(title)
        top.addStretch()
        self.btn_refresh = QPushButton("🔄 새로고침")
        self.btn_refresh.setStyleSheet("background:#319795; font-size:12px; padding:6px 12px;")
        self.btn_refresh.clicked.connect(self.manual_refresh)
        top.addWidget(self.btn_refresh)
        main.addLayout(top)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # ===== 탭1: 대출/반납 =====
        tab1 = QWidget()
        lay1 = QVBoxLayout(tab1)
        lay1.setSpacing(12)

        g_bc = QGroupBox("📷 바코드 스캔")
        v_bc = QVBoxLayout()
        h_bc = QHBoxLayout()
        self.entry_barcode = KoreanLineEdit("바코드 입력 후 Enter")
        self.entry_barcode.returnPressed.connect(self.on_barcode_enter)
        h_bc.addWidget(self.entry_barcode)
        btn_ok = QPushButton("확인")
        btn_ok.clicked.connect(self.safe_search)
        h_bc.addWidget(btn_ok)
        btn_clr = QPushButton("지우기")
        btn_clr.setStyleSheet("background:#4a5568;")
        btn_clr.clicked.connect(lambda: self.entry_barcode.clear())
        h_bc.addWidget(btn_clr)
        v_bc.addLayout(h_bc)
        g_bc.setLayout(v_bc)
        lay1.addWidget(g_bc)

        g_st = QGroupBox("👤 대여자 정보")
        v_st = QVBoxLayout()
        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("이름:"))
        self.entry_student = KoreanLineEdit("학생 이름")
        self.entry_student.returnPressed.connect(self.on_student_enter)
        h_name.addWidget(self.entry_student)
        v_st.addLayout(h_name)

        h_phone = QHBoxLayout()
        h_phone.addWidget(QLabel("핸드폰 끝 4자리:"))
        self.entry_phone = KoreanLineEdit("1234")
        self.entry_phone.setMaxLength(4)
        self.entry_phone.setValidator(QIntValidator(0, 9999))
        self.entry_phone.returnPressed.connect(self.on_student_enter)
        h_phone.addWidget(self.entry_phone)
        v_st.addLayout(h_phone)

        h_st_btn = QHBoxLayout()
        btn_st_ok = QPushButton("확인")
        btn_st_ok.clicked.connect(self.safe_check)
        h_st_btn.addWidget(btn_st_ok)
        btn_st_clr = QPushButton("지우기")
        btn_st_clr.setStyleSheet("background:#4a5568;")
        btn_st_clr.clicked.connect(self.clear_student)
        h_st_btn.addWidget(btn_st_clr)
        v_st.addLayout(h_st_btn)
        g_st.setLayout(v_st)
        lay1.addWidget(g_st)

        g_info = QGroupBox("📖 도서 정보")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)

        def row(r, text):
            k = QLabel(text)
            k.setStyleSheet("color:#a0aec0; font-weight:bold;")
            v = QLabel("-")
            v.setStyleSheet("font-weight:bold; font-size:13px;")
            grid.addWidget(k, r, 0)
            grid.addWidget(v, r, 1)
            return v

        self.lbl_title = row(0, "제      목 :")
        self.lbl_title.setStyleSheet("color:#63b3ed; font-weight:bold;")
        self.lbl_author = row(1, "저      자 :")
        self.lbl_ar = row(2, "AR Level :")
        self.lbl_lexile = row(3, "Lexile    :")
        self.lbl_quiz = row(4, "Quiz No  :")
        self.lbl_barcode = row(5, "바 코 드  :")
        self.lbl_loan = row(6, "대출 상태 :")
        self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
        g_info.setLayout(grid)
        lay1.addWidget(g_info)

        h_act = QHBoxLayout()
        btn_loan = QPushButton("📥 대출하기")
        btn_loan.setStyleSheet("background:#2b6cb0; font-size:15px; padding:12px;")
        btn_loan.clicked.connect(lambda: self.safe_process("RENT"))
        h_act.addWidget(btn_loan)
        btn_ret = QPushButton("📤 반납하기")
        btn_ret.setStyleSheet("background:#2f855a; font-size:15px; padding:12px;")
        btn_ret.clicked.connect(lambda: self.safe_process("RETURN"))
        h_act.addWidget(btn_ret)
        lay1.addLayout(h_act)

        self.lbl_status = QLabel("준비됨")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-weight:bold; color:#fc8181; font-size:13px; padding:6px;")
        lay1.addWidget(self.lbl_status)
        lay1.addStretch()
        tabs.addTab(tab1, "📋 대출/반납")

        # ===== 탭2: 현황 =====
        tab2 = QWidget()
        lay2 = QVBoxLayout(tab2)
        lay2.setSpacing(14)

        b1 = QPushButton("📋 전체 대출 현황")
        b1.setStyleSheet("background:#805ad5; font-size:15px; padding:14px;")
        b1.clicked.connect(self.show_loan_status)
        lay2.addWidget(b1)

        b2 = QPushButton("⚠️ 연체자 목록")
        b2.setStyleSheet("background:#e53e3e; font-size:15px; padding:14px;")
        b2.clicked.connect(self.show_overdue_list)
        lay2.addWidget(b2)

        b3 = QPushButton("📊 AR Level별 대여 가능 현황")
        b3.setStyleSheet("background:#319795; font-size:15px; padding:14px;")
        b3.clicked.connect(self.show_ar_status)
        lay2.addWidget(b3)

        lay2.addStretch()
        tabs.addTab(tab2, "📊 현황 조회")

        # ===== 탭3: 도서 관리 =====
        tab3 = QWidget()
        lay3 = QVBoxLayout(tab3)
        lay3.setSpacing(14)

        b_add = QPushButton("➕ 새 도서 등록")
        b_add.setStyleSheet("background:#dd6b20; font-size:15px; padding:14px;")
        b_add.clicked.connect(self.show_add_book)
        lay3.addWidget(b_add)

        b_del = QPushButton("🗑️ 도서 삭제")
        b_del.setStyleSheet("background:#9b2c2c; font-size:15px; padding:14px;")
        b_del.clicked.connect(self.show_delete_book)
        lay3.addWidget(b_del)

        lay3.addStretch()
        tabs.addTab(tab3, "📚 도서 관리")

        # ===== 탭4: 엑셀 =====
        tab4 = QWidget()
        lay4 = QVBoxLayout(tab4)
        lay4.setSpacing(14)

        b_ex1 = QPushButton("📊 대출 현황 엑셀 저장")
        b_ex1.setStyleSheet("background:#2b6cb0; font-size:15px; padding:14px;")
        b_ex1.clicked.connect(self.export_loan_excel)
        lay4.addWidget(b_ex1)

        b_ex2 = QPushButton("📜 전체 로그 엑셀 저장")
        b_ex2.setStyleSheet("background:#4a5568; font-size:15px; padding:14px;")
        b_ex2.clicked.connect(self.export_logs_excel)
        lay4.addWidget(b_ex2)

        lay4.addStretch()
        tabs.addTab(tab4, "📥 엑셀 저장")

        main.addWidget(tabs)

        self.lbl_bottom = QLabel()
        self.lbl_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(self.lbl_bottom)

        self.entry_barcode.setFocus()

    def clear_student(self):
        self.entry_student.clear()
        self.entry_phone.clear()
        self.entry_student.setFocus()

    def safe_search(self):
        self.force_commit_ime()
        QTimer.singleShot(80, self.search_book)

    def safe_check(self):
        self.force_commit_ime()
        QTimer.singleShot(80, self.check_student)

    def safe_process(self, action):
        self.force_commit_ime()
        QTimer.singleShot(80, lambda: self.process_action(action))

    def on_barcode_enter(self):
        if not self.entry_barcode.isComposing():
            self.safe_search()

    def on_student_enter(self):
        if not self.entry_student.isComposing() and not self.entry_phone.isComposing():
            self.safe_check()

    def search_book(self):
        code = self.entry_barcode.text().strip()
        if not code:
            return

        book = self.books_cache.get(code)
        if not book:
            self.load_books_cache()
            book = self.books_cache.get(code)

        if book:
            self.current_book = book
            self.lbl_title.setText(book.get("title", "-"))
            self.lbl_author.setText(book.get("author", "-"))
            self.lbl_ar.setText(str(book.get("ar_level", "-")))
            self.lbl_lexile.setText(str(book.get("lexile", "-")))
            self.lbl_quiz.setText(str(book.get("ar_quiz_no", "-")))
            self.lbl_barcode.setText(code)

            if code in self.loan_status:
                info = self.loan_status[code]
                self.lbl_loan.setText(f"대출 중 ({info['name']})")
                self.lbl_loan.setStyleSheet("color:#fc8181; font-weight:bold;")
                self.lbl_status.setText(f"[주의] '{info['name']}'님이 대출 중입니다.")
                self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            else:
                self.lbl_loan.setText("대출 가능")
                self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
                self.lbl_status.setText("도서 조회 성공. 학생 정보를 입력하세요.")
                self.lbl_status.setStyleSheet("color:#63b3ed; font-weight:bold;")
        else:
            self.current_book = None
            self.lbl_title.setText("등록되지 않은 도서입니다.")
            self.lbl_author.setText("-")
            self.lbl_ar.setText("-")
            self.lbl_lexile.setText("-")
            self.lbl_quiz.setText("-")
            self.lbl_barcode.setText(code)
            self.lbl_loan.setText("-")
            self.lbl_status.setText("[오류] 등록되지 않은 바코드입니다.")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")

        QTimer.singleShot(50, lambda: self.entry_student.setFocus())

    def check_student(self):
        sid = self.get_student_id()
        if not sid:
            self.lbl_status.setText("[경고] 이름과 핸드폰 끝 4자리를 모두 입력하세요!")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return

        count = self.get_student_loan_count(sid)
        titles = []
        overdue = []
        now = datetime.now()

        for bc, info in self.loan_status.items():
            if info["name"] == sid:
                titles.append(info.get("title") or bc)
                minutes = (now - info["date"]).total_seconds() / 60
                if minutes > OVERDUE_MINUTES:
                    overdue.append(f"{info.get('title') or bc} ({int(minutes)}분)")

        msg = f"'{sid}'님 현재 대출: {count}/{MAX_LOAN}권"
        if titles:
            msg += f"\n도서: {', '.join(titles)}"
        if overdue:
            msg += f"\n⚠️ 연체: {', '.join(overdue)}"
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
        else:
            self.lbl_status.setStyleSheet("color:#48bb78; font-weight:bold;")
        self.lbl_status.setText(msg)

    def process_action(self, action):
        if not self.current_book:
            self.lbl_status.setText("[경고] 먼저 도서를 조회해주세요!")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return

        sid = self.get_student_id()
        if not sid:
            self.lbl_status.setText("[경고] 이름과 핸드폰 끝 4자리를 모두 입력하세요!")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return

        barcode = str(self.current_book.get("barcode", ""))
        title = self.current_book.get("title", "")
        author = self.current_book.get("author", "")
        ar_level = str(self.current_book.get("ar_level", ""))

        self.rebuild_loan_status()

        if action == "RENT":
            if self.get_student_loan_count(sid) >= MAX_LOAN:
                QMessageBox.warning(self, "대출 제한",
                    f"'{sid}'님은 이미 최대 {MAX_LOAN}권을 대출 중입니다.")
                return
            if barcode in self.loan_status:
                holder = self.loan_status[barcode]["name"]
                QMessageBox.warning(self, "대출 불가", f"이미 '{holder}'님이 대출 중입니다.")
                return
        else:
            if barcode not in self.loan_status:
                QMessageBox.warning(self, "반납 불가", "대출 기록이 없는 도서입니다.")
                return
            if self.loan_status[barcode]["name"] != sid:
                QMessageBox.warning(self, "반납 불가",
                    f"'{self.loan_status[barcode]['name']}'님이 대출한 책입니다.")
                return

        try:
            log = {
                "date": datetime.now().isoformat(),
                "barcode": barcode,
                "student_name": sid,
                "action": action,
                "title": title,
                "author": author,
                "ar_level": ar_level,
            }
            supabase.table("logs").insert(log).execute()

            if action == "RENT":
                self.loan_status[barcode] = {
                    "name": sid, "date": datetime.now(), "title": title
                }
                self.lbl_loan.setText(f"대출 중 ({sid})")
                self.lbl_loan.setStyleSheet("color:#fc8181; font-weight:bold;")
                label = "대출"
            else:
                del self.loan_status[barcode]
                self.lbl_loan.setText("대출 가능 (반납됨)")
                self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
                label = "반납"

            self.lbl_status.setText(f"[{title}] {label} 완료! ({sid})")
            self.lbl_status.setStyleSheet("color:#63b3ed; font-weight:bold;")
            QMessageBox.information(self, "성공", f"[{title}] {label} 처리 완료\n대여자: {sid}")

            self.entry_barcode.clear()
            self.clear_student()
            self.entry_barcode.setFocus()
            self.update_status_bar()

        except Exception as e:
            QMessageBox.critical(self, "오류", f"처리 중 오류:\n{e}")

    def show_loan_status(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"현재 대출 현황 (총 {len(self.loan_status)}권)")
        dlg.resize(1000, 480)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QTableWidget { background:#2d3748; color:white; gridline-color:#4a5568; font-size:13px; }
            QHeaderView::section { background:#4a5568; color:white; font-weight:bold; padding:6px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:8px; }
        """)
        lay = QVBoxLayout(dlg)
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["바코드", "제목", "저자", "대출자", "대출일", "상태", "관리"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)

        rows = []
        now = datetime.now()
        for bc, info in self.loan_status.items():
            book = self.books_cache.get(bc, {})
            minutes = (now - info["date"]).total_seconds() / 60
            status = f"{int(minutes)}분 경과"
            if minutes > OVERDUE_MINUTES:
                status = f"⚠️ 연체 {int(minutes - OVERDUE_MINUTES)}분"
            rows.append([
                bc,
                info.get("title") or book.get("title", ""),
                book.get("author", ""),
                info["name"],
                info["date"].strftime("%Y-%m-%d %H:%M"),
                status,
            ])

        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 5 and "연체" in str(val):
                    item.setForeground(QBrush(QColor("#fc8181")))
                table.setItem(i, j, item)

            btn = QPushButton("반납")
            btn.setStyleSheet("background:#2f855a; font-size:11px; padding:4px;")
            bc, name = row[0], row[3]
            btn.clicked.connect(lambda _, b=bc, n=name, d=dlg: self.quick_return(b, n, d))
            table.setCellWidget(i, 6, btn)

        lay.addWidget(table)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.exec()

    def quick_return(self, barcode, student_id, dialog):
        reply = QMessageBox.question(
            dialog, "반납 확인",
            f"바코드 [{barcode}] 반납할까요?\n대여자: {student_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        book = self.books_cache.get(barcode, {})
        try:
            log = {
                "date": datetime.now().isoformat(),
                "barcode": barcode,
                "student_name": student_id,
                "action": "RETURN",
                "title": book.get("title", ""),
                "author": book.get("author", ""),
                "ar_level": str(book.get("ar_level", "")),
            }
            supabase.table("logs").insert(log).execute()
            if barcode in self.loan_status:
                del self.loan_status[barcode]
            QMessageBox.information(dialog, "성공", "반납 완료")
            dialog.accept()
            self.update_status_bar()
        except Exception as e:
            QMessageBox.critical(dialog, "오류", str(e))

    def show_overdue_list(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("연체자 목록")
        dlg.resize(900, 420)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QTableWidget { background:#2d3748; color:white; gridline-color:#4a5568; font-size:13px; }
            QHeaderView::section { background:#e53e3e; color:white; font-weight:bold; padding:6px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:8px; }
        """)
        lay = QVBoxLayout(dlg)

        items = []
        now = datetime.now()
        for bc, info in self.loan_status.items():
            minutes = (now - info["date"]).total_seconds() / 60
            if minutes > OVERDUE_MINUTES:
                items.append((bc, info, minutes))

        if not items:
            lbl = QLabel("현재 연체된 도서가 없습니다.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:16px; color:#68d391; padding:40px;")
            lay.addWidget(lbl)
        else:
            table = QTableWidget()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(
                ["바코드", "제목", "대출자", "대출일", "연체시간", "관리"]
            )
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setRowCount(len(items))

            for i, (bc, info, minutes) in enumerate(items):
                vals = [
                    bc,
                    info.get("title", ""),
                    info["name"],
                    info["date"].strftime("%Y-%m-%d %H:%M"),
                    f"{int(minutes - OVERDUE_MINUTES)}분 연체",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 4:
                        item.setForeground(QBrush(QColor("#fc8181")))
                    table.setItem(i, j, item)

                btn = QPushButton("반납")
                btn.setStyleSheet("background:#2f855a; font-size:11px; padding:4px;")
                btn.clicked.connect(
                    lambda _, b=bc, n=info["name"], d=dlg: self.quick_return(b, n, d)
                )
                table.setCellWidget(i, 5, btn)

            lay.addWidget(table)
            lbl = QLabel(f"총 연체: {len(items)}권")
            lbl.setStyleSheet("font-weight:bold; color:#fc8181;")
            lay.addWidget(lbl)

        btn = QPushButton("닫기")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def show_ar_status(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("AR Level별 대여 가능 현황")
        dlg.resize(500, 500)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QTableWidget { background:#2d3748; color:white; gridline-color:#4a5568; font-size:13px; }
            QHeaderView::section { background:#319795; color:white; font-weight:bold; padding:6px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:8px; }
        """)
        lay = QVBoxLayout(dlg)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["AR Level", "총 보유", "대출 중", "대출 가능"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)

        ranges = defaultdict(lambda: {"total": 0, "rented": 0})
        for bc, book in self.books_cache.items():
            try:
                ar = float(book.get("ar_level", 0))
            except:
                ar = 0.0
            key = f"{int(ar * 10) / 10.0:.1f}"
            ranges[key]["total"] += 1
            if bc in self.loan_status:
                ranges[key]["rented"] += 1

        keys = sorted(ranges.keys(), key=lambda x: float(x))
        table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            total = ranges[k]["total"]
            rented = ranges[k]["rented"]
            avail = total - rented
            for j, val in enumerate([k, f"{total}권", f"{rented}권", f"{avail}권"]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    item.setForeground(QBrush(QColor("#68d391" if avail > 0 else "#fc8181")))
                table.setItem(i, j, item)

        lay.addWidget(table)
        btn = QPushButton("닫기")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def show_add_book(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("새 도서 등록")
        dlg.resize(420, 400)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QLineEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:4px; padding:8px; }
            QLabel { font-weight:bold; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:10px; }
        """)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        fields = {}
        for label, key, ph in [
            ("바코드", "barcode", "바코드"),
            ("제목", "title", "책 제목"),
            ("저자", "author", "저자"),
            ("AR Level", "ar_level", "2.3"),
            ("Lexile (선택)", "lexile", "450L"),
            ("Quiz No (선택)", "ar_quiz_no", ""),
        ]:
            lay.addWidget(QLabel(label))
            e = KoreanLineEdit(ph)
            fields[key] = e
            lay.addWidget(e)

        h = QHBoxLayout()
        btn_save = QPushButton("저장")
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background:#4a5568;")
        h.addWidget(btn_save)
        h.addWidget(btn_cancel)
        lay.addLayout(h)

        def save():
            barcode = fields["barcode"].text().strip()
            title = fields["title"].text().strip()
            author = fields["author"].text().strip()
            ar = fields["ar_level"].text().strip()
            if not barcode or not title or not author or not ar:
                QMessageBox.warning(dlg, "입력 오류", "바코드, 제목, 저자, AR Level은 필수입니다.")
                return
            try:
                data = {
                    "barcode": barcode,
                    "title": title,
                    "author": author,
                    "ar_level": float(ar),
                    "lexile": fields["lexile"].text().strip(),
                    "ar_quiz_no": fields["ar_quiz_no"].text().strip(),
                }
                supabase.table("books").insert(data).execute()
                self.books_cache[barcode] = data
                QMessageBox.information(dlg, "완료", f"등록 완료\n{title}")
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "오류", str(e))

        btn_save.clicked.connect(save)
        btn_cancel.clicked.connect(dlg.reject)
        fields["barcode"].setFocus()
        dlg.exec()

    def show_delete_book(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("도서 삭제")
        dlg.resize(400, 200)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QLineEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:4px; padding:8px; }
            QPushButton { background:#9b2c2c; color:white; border-radius:4px; font-weight:bold; padding:10px; }
        """)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("삭제할 바코드 입력"))
        entry = KoreanLineEdit("바코드")
        lay.addWidget(entry)

        h = QHBoxLayout()
        btn_del = QPushButton("삭제")
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background:#4a5568;")
        h.addWidget(btn_del)
        h.addWidget(btn_cancel)
        lay.addLayout(h)

        def do_delete():
            bc = entry.text().strip()
            if not bc:
                return
            book = self.books_cache.get(bc)
            if not book:
                QMessageBox.warning(dlg, "오류", "해당 도서를 찾을 수 없습니다.")
                return
            if bc in self.loan_status:
                QMessageBox.warning(dlg, "삭제 불가", "대출 중인 도서는 삭제할 수 없습니다.")
                return
            reply = QMessageBox.question(
                dlg, "확인",
                f"정말 삭제할까요?\n{book.get('title')} ({bc})",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                supabase.table("books").delete().eq("barcode", bc).execute()
                self.books_cache.pop(bc, None)
                QMessageBox.information(dlg, "완료", "삭제되었습니다.")
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "오류", str(e))

        btn_del.clicked.connect(do_delete)
        btn_cancel.clicked.connect(dlg.reject)
        entry.setFocus()
        dlg.exec()

    def export_loan_excel(self):
        if not self.loan_status:
            QMessageBox.information(self, "알림", "대출 중인 도서가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", f"대출현황_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            data = []
            for bc, info in self.loan_status.items():
                book = self.books_cache.get(bc, {})
                data.append({
                    "바코드": bc,
                    "제목": info.get("title") or book.get("title", ""),
                    "저자": book.get("author", ""),
                    "AR Level": book.get("ar_level", ""),
                    "대출자": info["name"],
                    "대출일시": info["date"].strftime("%Y-%m-%d %H:%M"),
                })
            pd.DataFrame(data).to_excel(path, index=False)
            QMessageBox.information(self, "성공", f"저장 완료\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def export_logs_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", f"전체로그_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            res = supabase.table("logs").select("*").order("date").execute()
            if not res.data:
                QMessageBox.information(self, "알림", "로그가 없습니다.")
                return
            pd.DataFrame(res.data).to_excel(path, index=False)
            QMessageBox.information(self, "성공", f"저장 완료\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LibraryApp()
    window.show()
    sys.exit(app.exec())
