# app.py
from collections import defaultdict
from datetime import datetime
import sys
import pandas as pd
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

import config
import db
from utils import KoreanLineEdit


class LibraryApp(QWidget):

    def __init__(self):
        super().__init__()
        self.books_cache = {}
        self.loan_status = {}
        self.current_book = None
        self.continuous_mode = True

        self.migrate_existing_loans_if_needed()

        self.init_ui()
        self.full_sync()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.background_sync)
        self.poll_timer.start(config.POLL_INTERVAL_MS)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start(1000)

    def require_admin(self, action_name="관리자 기능"):
        pw, ok = QInputDialog.getText(
            self,
            "관리자 확인",
            f"{action_name}\n관리자 비밀번호를 입력하세요:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return False
        if pw != config.ADMIN_PASSWORD:
            QMessageBox.warning(self, "인증 실패", "비밀번호가 올바르지 않습니다.")
            return False
        return True

    def migrate_existing_loans_if_needed(self):
        try:
            res = db.check_current_loans_exist()
            if res and not res.data:
                logs_data = db.fetch_logs_for_migration()
                state = {}
                for log in (logs_data or []):
                    bc = str(log.get("barcode", ""))
                    if not bc:
                        continue
                    action = log.get("action")
                    if action == "RENT":
                        state[bc] = {
                            "barcode": bc,
                            "title": log.get("title", ""),
                            "student_name": log.get("student_name", ""),
                            "borrow_date": log.get("date"),
                        }
                    elif action == "RETURN":
                        if bc in state:
                            del state[bc]

                items_to_insert = list(state.values())
                items_to_insert.append({
                    "barcode": config.MIGRATED_MARKER,
                    "title": "SYSTEM_MARKER",
                    "student_name": "SYSTEM",
                    "borrow_date": datetime.now().isoformat(),
                })
                db.upsert_current_loans(items_to_insert)
        except Exception as e:
            print(f"마이그레이션 체크 중 예외 발생: {e}")

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
            print(f"[백그라운드 동기화 실패] {e}")

    def manual_refresh(self):
        self.btn_refresh.setEnabled(False)
        try:
            self.full_sync()
            self.lbl_status.setText(
                f"[새로고침 완료] 최신 상태 동기화됨 ({datetime.now().strftime('%H:%M:%S')})"
            )
            self.lbl_status.setStyleSheet("color:#63b3ed; font-weight:bold;")
        except Exception as e:
            self.lbl_status.setText(f"[새로고침 실패] {e}")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
        finally:
            self.btn_refresh.setEnabled(True)

    def load_books_cache(self):
        self.books_cache = db.fetch_books()

    def rebuild_loan_status(self):
        rows = db.fetch_current_loans()
        status = {}
        for row in rows:
            bc = str(row.get("barcode", ""))
            if not bc or bc == config.MIGRATED_MARKER:
                continue
            date_str = row.get("borrow_date", "")
            try:
                loan_date = datetime.fromisoformat(
                    str(date_str).replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                loan_date = datetime.now()
            status[bc] = {
                "name": row.get("student_name", ""),
                "date": loan_date,
                "title": row.get("title", ""),
            }
        self.loan_status = status

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
            1
            for v in self.loan_status.values()
            if (now - v["date"]).total_seconds() / 60 > config.OVERDUE_MINUTES
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
        mode = "연속 ON" if self.continuous_mode else "연속 OFF"
        self.lbl_bottom.setText(
            f"전체 대출: {total}권  |  연체 도서: {overdue}권  |  학생별 최대"
            f" {config.MAX_LOAN}권 제한  |  {mode}  |  시스템 정상 작동중"
        )
        if overdue > 0:
            self.lbl_bottom.setStyleSheet(
                "background:#742a2a; color:#fed7d7; font-weight:bold; font-size:13px;"
                " padding:10px; border-radius:6px;"
            )
        else:
            self.lbl_bottom.setStyleSheet(
                "background:#2d3748; color:#a0aec0; font-weight:bold; font-size:13px;"
                " padding:10px; border-radius:6px;"
            )

    def init_ui(self):
        self.setWindowTitle("에피토미에듀 도서관 시스템")
        self.resize(620, 820)
        self.setStyleSheet("""
            QWidget { background:#1a202c; color:#e2e8f0; font-family:'Apple SD Gothic Neo',sans-serif; }
            QLineEdit, QTextEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:6px; padding:8px; font-size:14px; }
            QPushButton { background:#3182ce; color:white; border-radius:6px; font-weight:bold; font-size:13px; padding:10px; }
            QPushButton:hover { background:#2b6cb0; }
            QLabel { font-size:13px; }
            QCheckBox { color:#e2e8f0; font-size:13px; }
            QTabWidget::pane { border:1px solid #4a5568; border-radius:8px; }
            QTabBar::tab { background:#2d3748; color:#a0aec0; padding:10px 14px; margin-right:4px;
                           border-top-left-radius:8px; border-top-right-radius:8px; font-weight:bold; }
            QTabBar::tab:selected { background:#3182ce; color:white; }
            QGroupBox { border:1px solid #4a5568; border-radius:8px; margin-top:12px; font-weight:bold; color:#90cdf4; padding-top:10px; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; }
        """)

        main = QVBoxLayout(self)
        main.setSpacing(10)
        main.setContentsMargins(14, 14, 14, 14)

        top = QHBoxLayout()
        title = QLabel("📚 에피토미에듀 통합 도서 관리 시스템")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#63b3ed;")
        top.addWidget(title)
        top.addStretch()
        self.btn_refresh = QPushButton("🔄 새로고침")
        self.btn_refresh.setStyleSheet(
            "background:#319795; font-size:12px; padding:6px 12px;"
        )
        self.btn_refresh.clicked.connect(self.manual_refresh)
        top.addWidget(self.btn_refresh)
        main.addLayout(top)

        # ★ self.tabs 로 변경
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # ===== 탭 1: 대출 / 반납 =====
        tab1 = QWidget()
        lay1 = QVBoxLayout(tab1)
        lay1.setSpacing(10)

        g_bc = QGroupBox("도서 바코드 스캔")
        v_bc = QVBoxLayout()
        h_bc = QHBoxLayout()
        self.entry_barcode = KoreanLineEdit("도서 바코드를 스캔하세요")
        self.entry_barcode.returnPressed.connect(self.on_barcode_enter)
        h_bc.addWidget(self.entry_barcode)
        btn_ok = QPushButton("조회")
        btn_ok.clicked.connect(self.safe_search)
        h_bc.addWidget(btn_ok)
        btn_clr = QPushButton("지우기")
        btn_clr.setStyleSheet("background:#4a5568;")
        btn_clr.clicked.connect(lambda: self.entry_barcode.clear())
        h_bc.addWidget(btn_clr)
        v_bc.addLayout(h_bc)

        self.chk_continuous = QCheckBox("연속 작업 모드 (체크 시 바코드 자동 초기화)")
        self.chk_continuous.setChecked(True)
        self.chk_continuous.toggled.connect(self.on_continuous_toggled)
        v_bc.addWidget(self.chk_continuous)
        g_bc.setLayout(v_bc)
        lay1.addWidget(g_bc)

        g_st = QGroupBox("학생 정보 입력")
        v_st = QVBoxLayout()
        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("이름:"))
        self.entry_student = KoreanLineEdit("학생 이름 입력")
        self.entry_student.returnPressed.connect(self.on_student_enter)
        h_name.addWidget(self.entry_student)
        v_st.addLayout(h_name)
        h_phone = QHBoxLayout()
        h_phone.addWidget(QLabel("전화번호 뒷 4자리:"))
        self.entry_phone = KoreanLineEdit("예: 1234")
        self.entry_phone.setMaxLength(4)
        self.entry_phone.setValidator(QIntValidator(0, 9999))
        self.entry_phone.returnPressed.connect(self.on_student_enter)
        h_phone.addWidget(self.entry_phone)
        v_st.addLayout(h_phone)
        h_st_btn = QHBoxLayout()
        btn_st_ok = QPushButton("학생 확인")
        btn_st_ok.clicked.connect(self.safe_check)
        h_st_btn.addWidget(btn_st_ok)
        btn_st_clr = QPushButton("정보 초기화")
        btn_st_clr.setStyleSheet("background:#4a5568;")
        btn_st_clr.clicked.connect(self.clear_student)
        h_st_btn.addWidget(btn_st_clr)
        v_st.addLayout(h_st_btn)
        g_st.setLayout(v_st)
        lay1.addWidget(g_st)

        g_info = QGroupBox("도서 상세 정보")
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

        self.lbl_title = row(0, "도서명        :")
        self.lbl_title.setStyleSheet("color:#63b3ed; font-weight:bold;")
        self.lbl_author = row(1, "저자 / 출판사 :")
        self.lbl_ar = row(2, "AR Level      :")
        self.lbl_lexile = row(3, "Lexile        :")
        self.lbl_quiz = row(4, "Quiz No       :")
        self.lbl_barcode = row(5, "바코드        :")
        self.lbl_loan = row(6, "현재 대출상태 :")
        self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
        g_info.setLayout(grid)
        lay1.addWidget(g_info)

        h_act = QHBoxLayout()
        btn_loan = QPushButton("📖 대출 처리")
        btn_loan.setStyleSheet("background:#2b6cb0; font-size:15px; padding:12px;")
        btn_loan.clicked.connect(lambda: self.safe_process("RENT"))
        h_act.addWidget(btn_loan)

        btn_ret = QPushButton("🔄 반납 처리")
        btn_ret.setStyleSheet("background:#2f855a; font-size:15px; padding:12px;")
        btn_ret.clicked.connect(lambda: self.safe_process("RETURN"))
        h_act.addWidget(btn_ret)
        lay1.addLayout(h_act)

        self.lbl_status = QLabel("준비 완료")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            "font-weight:bold; color:#fc8181; font-size:13px; padding:6px;"
        )
        lay1.addWidget(self.lbl_status)
        lay1.addStretch()
        self.tabs.addTab(tab1, "대출 / 반납")

        # ===== 탭 2: 통계 및 조회 =====
        tab2 = QWidget()
        lay2 = QVBoxLayout(tab2)
        lay2.setSpacing(12)

        b_dash = QPushButton("📊 금일 대출/반납 현황 대시보드")
        b_dash.setStyleSheet("background:#d69e2e; font-size:15px; padding:14px;")
        b_dash.clicked.connect(self.show_today_dashboard)
        lay2.addWidget(b_dash)

        b_search = QPushButton("🔍 학생별 대출 현황 조회 (이름/번호)")
        b_search.setStyleSheet("background:#3182ce; font-size:15px; padding:14px;")
        b_search.clicked.connect(self.show_student_search)
        lay2.addWidget(b_search)

        b1 = QPushButton("📋 현재 대출 중인 도서 전체 목록")
        b1.setStyleSheet("background:#805ad5; font-size:15px; padding:14px;")
        b1.clicked.connect(self.show_loan_status)
        lay2.addWidget(b1)

        b2 = QPushButton("🚨 연체 도서 목록 + 문자 안내 생성기")
        b2.setStyleSheet("background:#e53e3e; font-size:15px; padding:14px;")
        b2.clicked.connect(self.show_overdue_list)
        lay2.addWidget(b2)

        b3 = QPushButton("📈 AR Level 별 장서 현황표")
        b3.setStyleSheet("background:#319795; font-size:15px; padding:14px;")
        b3.clicked.connect(self.show_ar_status)
        lay2.addWidget(b3)

        lay2.addStretch()
        self.tabs.addTab(tab2, "통계 및 조회")

        # ===== 탭 3: 도서 관리 =====
        tab3 = QWidget()
        lay3 = QVBoxLayout(tab3)
        lay3.setSpacing(14)

        hint = QLabel("※ 등록·삭제·일괄등록은 관리자 비밀번호가 필요합니다.")
        hint.setStyleSheet("color:#a0aec0; font-size:12px;")
        lay3.addWidget(hint)

        b_add = QPushButton("➕ 신규 도서 등록")
        b_add.setStyleSheet("background:#dd6b20; font-size:15px; padding:14px;")
        b_add.clicked.connect(self.on_add_book_clicked)
        lay3.addWidget(b_add)

        b_bulk = QPushButton("📥 도서 일괄 등록 (엑셀/CSV)")
        b_bulk.setStyleSheet("background:#38a169; font-size:15px; padding:14px;")
        b_bulk.clicked.connect(self.on_bulk_add_clicked)
        lay3.addWidget(b_bulk)

        b_del = QPushButton("🗑️ 도서 정보 삭제")
        b_del.setStyleSheet("background:#9b2c2c; font-size:15px; padding:14px;")
        b_del.clicked.connect(self.on_delete_book_clicked)
        lay3.addWidget(b_del)

        lay3.addStretch()
        self.tabs.addTab(tab3, "도서 관리")

        # ===== 탭 4: 데이터 관리 =====
        tab4 = QWidget()
        lay4 = QVBoxLayout(tab4)
        lay4.setSpacing(14)
        b_ex1 = QPushButton("📥 현재 대출 현황 엑셀 다운로드")
        b_ex1.setStyleSheet("background:#2b6cb0; font-size:15px; padding:14px;")
        b_ex1.clicked.connect(self.export_loan_excel)
        lay4.addWidget(b_ex1)
        b_ex2 = QPushButton("📥 전체 대출/반납 로그 엑셀 다운로드")
        b_ex2.setStyleSheet("background:#4a5568; font-size:15px; padding:14px;")
        b_ex2.clicked.connect(self.export_logs_excel)
        lay4.addWidget(b_ex2)
        lay4.addStretch()
        self.tabs.addTab(tab4, "데이터 관리")

        main.addWidget(self.tabs)
        self.lbl_bottom = QLabel()
        self.lbl_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(self.lbl_bottom)
        self.entry_barcode.setFocus()

    def on_continuous_toggled(self, checked):
        self.continuous_mode = checked
        self.update_status_bar()

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
        if (
            not self.entry_student.isComposing()
            and not self.entry_phone.isComposing()
        ):
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
                self.lbl_loan.setText(f"대출중 ({info['name']})")
                self.lbl_loan.setStyleSheet("color:#fc8181; font-weight:bold;")
                self.lbl_status.setText(
                    f"[대출중 도서] '{info['name']}'님이 이미 대출 중인 도서입니다."
                )
                self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            else:
                self.lbl_loan.setText("대출 가능")
                self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
                self.lbl_status.setText("대출 가능한 도서입니다. 학생 정보를 확인하세요.")
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
            self.lbl_status.setText("[오류] 데이터베이스에 없는 바코드입니다.")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
        QTimer.singleShot(50, lambda: self.entry_student.setFocus())

    def check_student(self):
        sid = self.get_student_id()
        if not sid:
            self.lbl_status.setText(
                "[입력 오류] 학생 이름과 전화번호 뒷 4자리를 모두 입력하세요!"
            )
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return
        count = self.get_student_loan_count(sid)
        titles, overdue = [], []
        now = datetime.now()
        for bc, info in self.loan_status.items():
            if info["name"] == sid:
                titles.append(info.get("title") or bc)
                minutes = (now - info["date"]).total_seconds() / 60
                if minutes > config.OVERDUE_MINUTES:
                    overdue.append(f"{info.get('title') or bc} ({int(minutes)}분)")
        msg = f"'{sid}' 학생 대출 현황: {count}/{config.MAX_LOAN}권"
        if titles:
            msg += f"\n대출 목록: {', '.join(titles)}"
        if overdue:
            msg += f"\n[연체 도서 존재]: {', '.join(overdue)}"
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
        else:
            self.lbl_status.setStyleSheet("color:#48bb78; font-weight:bold;")
        self.lbl_status.setText(msg)

    def process_action(self, action):
        if not self.current_book:
            self.lbl_status.setText("[오류] 먼저 도서를 조회/스캔하세요!")
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return
        sid = self.get_student_id()
        if not sid:
            self.lbl_status.setText(
                "[입력 오류] 학생 이름과 전화번호 뒷 4자리를 모두 입력하세요!"
            )
            self.lbl_status.setStyleSheet("color:#fc8181; font-weight:bold;")
            return

        barcode = str(self.current_book.get("barcode", ""))
        title = self.current_book.get("title", "")
        author = self.current_book.get("author", "")
        ar_level = str(self.current_book.get("ar_level", ""))
        self.rebuild_loan_status()

        if action == "RENT":
            if self.get_student_loan_count(sid) >= config.MAX_LOAN:
                QMessageBox.warning(
                    self,
                    "대출 제한 초과",
                    f"'{sid}' 학생은 최대 대출 권수({config.MAX_LOAN}권)를 초과했습니다.",
                )
                return
            if barcode in self.loan_status:
                QMessageBox.warning(
                    self,
                    "대출 불가",
                    f"이미 '{self.loan_status[barcode]['name']}'님이 대출 중인 도서입니다.",
                )
                return
        else:
            if barcode not in self.loan_status:
                QMessageBox.warning(self, "반납 불가", "현재 대출 중인 도서가 아닙니다.")
                return
            if self.loan_status[barcode]["name"] != sid:
                QMessageBox.warning(
                    self,
                    "반납자 불일치",
                    f"'{self.loan_status[barcode]['name']}'님이 대출 중인 도서입니다.",
                )
                return

        try:
            now = datetime.now()
            log = {
                "date": now.isoformat(),
                "barcode": barcode,
                "student_name": sid,
                "action": action,
                "title": title,
                "author": author,
                "ar_level": ar_level,
            }
            db.insert_log(log)

            if action == "RENT":
                db.insert_current_loan({
                    "barcode": barcode,
                    "title": title,
                    "student_name": sid,
                    "borrow_date": now.isoformat(),
                })
                self.loan_status[barcode] = {"name": sid, "date": now, "title": title}
                self.lbl_loan.setText(f"대출중 ({sid})")
                self.lbl_loan.setStyleSheet("color:#fc8181; font-weight:bold;")
                label = "대출"
            else:
                db.delete_current_loan(barcode)
                if barcode in self.loan_status:
                    del self.loan_status[barcode]
                self.lbl_loan.setText("대출 가능 (반납 완료)")
                self.lbl_loan.setStyleSheet("color:#48bb78; font-weight:bold;")
                label = "반납"

            self.lbl_status.setText(f"[{title}] {label} 처리 완료! ({sid})")
            self.lbl_status.setStyleSheet("color:#63b3ed; font-weight:bold;")

            if self.continuous_mode:
                self.entry_barcode.clear()
                self.entry_barcode.setFocus()
            else:
                QMessageBox.information(
                    self, "처리 완료", f"[{title}] {label} 완료\n대상: {sid}"
                )
                self.entry_barcode.clear()
                self.clear_student()
                self.entry_barcode.setFocus()

            self.update_status_bar()
        except Exception as e:
            QMessageBox.critical(self, "서버 오류", f"처리 중 오류가 발생했습니다:\n{e}")

    def show_today_dashboard(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("금일 대출/반납 현황 대시보드")
        dlg.resize(420, 320)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QLabel { font-size:15px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:10px; }
        """)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(16)

        today = datetime.now().date()
        today_rent = 0
        today_return = 0
        try:
            logs_data = db.fetch_logs()
            for row in (logs_data or []):
                try:
                    d = (
                        datetime.fromisoformat(
                            str(row.get("date", "")).replace("Z", "+00:00")
                        )
                        .replace(tzinfo=None)
                        .date()
                    )
                except Exception:
                    continue
                if d == today:
                    if row.get("action") == "RENT":
                        today_rent += 1
                    elif row.get("action") == "RETURN":
                        today_return += 1
        except Exception as e:
            print(e)

        overdue = self.get_overdue_count()
        total_loan = len(self.loan_status)

        def card(text, color):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"background:#2d3748; color:{color}; font-size:18px;"
                " font-weight:bold; padding:18px; border-radius:10px;"
            )
            return lbl

        lay.addWidget(card(f"📥 오늘 총 대출 건수: {today_rent}건", "#63b3ed"))
        lay.addWidget(card(f"📤 오늘 총 반납 건수: {today_return}건", "#68d391"))
        lay.addWidget(card(f"📚 현재 총 대출 중 도서: {total_loan}권", "#a0aec0"))
        lay.addWidget(card(f"🚨 현재 연체 도서: {overdue}권", "#fc8181"))

        btn = QPushButton("확인")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def show_student_search(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("학생별 대출 현황 조회")
        dlg.resize(700, 480)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QLineEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:4px; padding:8px; }
            QTableWidget { background:#2d3748; color:white; gridline-color:#4a5568; font-size:13px; }
            QHeaderView::section { background:#4a5568; color:white; font-weight:bold; padding:6px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:8px; }
        """)
        lay = QVBoxLayout(dlg)

        h = QHBoxLayout()
        entry_name = KoreanLineEdit("학생 이름 (부분 검색)")
        entry_phone = KoreanLineEdit("전화번호 뒷 4자리 (선택)")
        entry_phone.setMaxLength(4)
        entry_phone.setValidator(QIntValidator(0, 9999))
        btn_go = QPushButton("검색")
        h.addWidget(entry_name)
        h.addWidget(entry_phone)
        h.addWidget(btn_go)
        lay.addLayout(h)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["학생 이름", "바코드", "도서명", "대출 일시", "대여 상태"]
        )
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)
        lay.addWidget(table)

        lbl_msg = QLabel("검색어를 입력하고 조회 버튼을 누르세요.")
        lbl_msg.setStyleSheet("color:#a0aec0;")
        lay.addWidget(lbl_msg)

        def do_search():
            name_q = entry_name.text().strip()
            phone_q = entry_phone.text().strip()
            if not name_q and not phone_q:
                QMessageBox.warning(dlg, "알림", "이름 또는 전화번호를 입력하세요.")
                return

            now = datetime.now()
            rows = []
            for bc, info in self.loan_status.items():
                sid = info["name"]
                match = True
                if name_q and name_q not in sid:
                    match = False
                if phone_q and f"({phone_q})" not in sid:
                    match = False
                if not match:
                    continue
                minutes = (now - info["date"]).total_seconds() / 60
                status = f"정상 ({int(minutes)}분 경과)"
                if minutes > config.OVERDUE_MINUTES:
                    status = f"🚨 연체 ({int(minutes - config.OVERDUE_MINUTES)}분 초과)"
                rows.append([
                    sid,
                    bc,
                    info.get("title", ""),
                    info["date"].strftime("%Y-%m-%d %H:%M"),
                    status,
                ])

            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    item = QTableWidgetItem(str(val))
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 4 and "연체" in str(val):
                        item.setForeground(QBrush(QColor("#fc8181")))
                    table.setItem(i, j, item)

            if rows:
                lbl_msg.setText(f"검색 결과: 총 {len(rows)}건")
                lbl_msg.setStyleSheet("color:#68d391; font-weight:bold;")
            else:
                lbl_msg.setText("검색 결과가 없습니다.")
                lbl_msg.setStyleSheet("color:#a0aec0;")

        btn_go.clicked.connect(do_search)
        entry_name.returnPressed.connect(do_search)
        entry_phone.returnPressed.connect(do_search)

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        entry_name.setFocus()
        dlg.exec()

    def show_loan_status(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"현재 대출 중인 도서 전체 목록 (총 {len(self.loan_status)}권)")
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
        table.setHorizontalHeaderLabels([
            "바코드",
            "도서명",
            "저자",
            "대출자",
            "대출 일시",
            "상태",
            "빠른 반납",
        ])
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)

        rows = []
        now = datetime.now()
        for bc, info in self.loan_status.items():
            book = self.books_cache.get(bc, {})
            minutes = (now - info["date"]).total_seconds() / 60
            status = f"정상 ({int(minutes)}분)"
            if minutes > config.OVERDUE_MINUTES:
                status = f"🚨 연체 ({int(minutes - config.OVERDUE_MINUTES)}분)"
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
            btn.clicked.connect(
                lambda _, b=bc, n=name, d=dlg, t=table: self.quick_return(
                    b, n, d, t
                )
            )
            table.setCellWidget(i, 6, btn)

        lay.addWidget(table)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.exec()

    def quick_return(self, barcode, student_id, dialog, table=None):
        reply = QMessageBox.question(
            dialog,
            "반납 확인",
            f"도서를 반납 처리하시겠습니까?\n바코드: [{barcode}]\n대출자: {student_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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
            db.insert_log(log)
            db.delete_current_loan(barcode)

            if barcode in self.loan_status:
                del self.loan_status[barcode]

            QMessageBox.information(dialog, "완료", "반납 처리가 완료되었습니다.")
            self.update_status_bar()

            if table is not None:
                self._refresh_loan_table(table, dialog)
            else:
                dialog.accept()
        except Exception as e:
            QMessageBox.critical(dialog, "오류", str(e))

    def _refresh_loan_table(self, table, dialog):
        table.setRowCount(0)
        rows = []
        now = datetime.now()

        for bc, info in self.loan_status.items():
            book = self.books_cache.get(bc, {})
            minutes = (now - info["date"]).total_seconds() / 60
            status = f"정상 ({int(minutes)}분)"
            if minutes > config.OVERDUE_MINUTES:
                status = f"🚨 연체 ({int(minutes - config.OVERDUE_MINUTES)}분)"
            rows.append([
                bc,
                info.get("title") or book.get("title", ""),
                book.get("author", ""),
                info["name"],
                info["date"].strftime("%Y-%m-%d %H:%M"),
                status,
            ])

        table.setRowCount(len(rows))
        dialog.setWindowTitle(
            f"현재 대출 중인 도서 전체 목록 (총 {len(self.loan_status)}권)"
        )

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
            btn.clicked.connect(
                lambda _, b=bc, n=name, d=dialog, t=table: self.quick_return(
                    b, n, d, t
                )
            )
            table.setCellWidget(i, 6, btn)

    def show_overdue_list(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("연체 도서 목록 및 빠른 반납 / 문자 안내")
        dlg.resize(950, 540)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QTableWidget { background:#2d3748; color:white; gridline-color:#4a5568; font-size:13px; }
            QHeaderView::section { background:#4a5568; color:white; font-weight:bold; padding:6px; }
            QTextEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:4px; padding:8px; font-size:13px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:8px; }
        """)
        lay = QVBoxLayout(dlg)

        def get_overdue_items():
            now = datetime.now()
            items = []
            for bc, info in self.loan_status.items():
                minutes = (now - info["date"]).total_seconds() / 60
                if minutes > config.OVERDUE_MINUTES:
                    book = self.books_cache.get(bc, {})
                    items.append({
                        "barcode": bc,
                        "title": info.get("title") or book.get("title", ""),
                        "name": info["name"],
                        "date": info["date"],
                        "overdue_mins": int(minutes - config.OVERDUE_MINUTES),
                    })
            return items

        overdue_items = get_overdue_items()

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "학생 이름",
            "바코드",
            "도서명",
            "대출 일시",
            "초과 시간",
            "빠른 반납",
        ])
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)

        def populate_table():
            nonlocal overdue_items
            overdue_items = get_overdue_items()
            table.setRowCount(len(overdue_items))
            for i, item_data in enumerate(overdue_items):
                row_vals = [
                    item_data["name"],
                    item_data["barcode"],
                    item_data["title"],
                    item_data["date"].strftime("%Y-%m-%d %H:%M"),
                    f"{item_data['overdue_mins']}분 초과",
                ]
                for j, val in enumerate(row_vals):
                    item = QTableWidgetItem(str(val))
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 4:
                        item.setForeground(QBrush(QColor("#fc8181")))
                    table.setItem(i, j, item)

                btn = QPushButton("반납")
                btn.setStyleSheet("background:#2f855a; font-size:11px; padding:4px;")
                bc, name = item_data["barcode"], item_data["name"]
                btn.clicked.connect(
                    lambda _, b=bc, n=name: (self.quick_return(b, n, dlg), populate_table())
                )
                table.setCellWidget(i, 5, btn)

        populate_table()
        lay.addWidget(table)

        lay.addWidget(
            QLabel("💬 선택한 연체 학생에게 발송할 안내 문자 메시지 템플릿:")
        )
        txt_msg = QTextEdit()
        txt_msg.setPlaceholderText(
            "표에서 학생을 클릭하면 맞춤형 문자 메시지가 생성됩니다."
        )
        txt_msg.setMaximumHeight(120)
        lay.addWidget(txt_msg)

        def on_row_clicked(row, col):
            if row < 0 or row >= len(overdue_items):
                return
            item = overdue_items[row]
            msg = (
                f"[에피토미에듀 도서관]\n안녕하세요, {item['name']} 학부모님"
                f"님.\n현재 대출 중인 도서 '[{item['title']}]'이(가) 반납 기한을"
                f" 초과하였습니다.\n(초과 시간: 약 {item['overdue_mins']}분"
                " 경과)\n빠른 반납 협조 부탁드립니다. 감사합니다!"
            )
            txt_msg.setText(msg)

        table.cellClicked.connect(on_row_clicked)

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.exec()

    def show_ar_status(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("AR Level 별 장서 현황표 (트리 구조)")
        dlg.resize(820, 580)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QTreeWidget {
                background:#2d3748;
                color:white;
                border:1px solid #4a5568;
                font-size:13px;
                outline:0;
            }
            QTreeWidget::item { padding:4px 2px; }
            QTreeWidget::item:selected { background:#3182ce; }
            QHeaderView::section {
                background:#4a5568;
                color:white;
                font-weight:bold;
                padding:6px;
                border:none;
            }
            QPushButton {
                background:#3182ce;
                color:white;
                border-radius:4px;
                font-weight:bold;
                padding:8px 14px;
            }
            QPushButton:hover { background:#2b6cb0; }
            QLabel { color:#a0aec0; font-size:13px; }
        """)
        lay = QVBoxLayout(dlg)

        # ===== 데이터 준비 =====
        range_detail = defaultdict(lambda: defaultdict(list))
        total_books = len(self.books_cache)

        for book in self.books_cache.values():
            ar = book.get("ar_level")
            if ar is not None and str(ar).strip() != "" and str(ar) != "-":
                try:
                    val = float(ar)
                    range_key = f"AR {int(val)}점대"
                    exact = f"{val:.1f}"
                    range_detail[range_key][exact].append(book)
                except Exception:
                    range_detail["미분류 / 미지정"][str(ar)].append(book)
            else:
                range_detail["미분류 / 미지정"]["미지정"].append(book)

        # ===== 트리 위젯 =====
        tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels(["항목", "권수", "점유율 (%)", "비고"])
        tree.setColumnWidth(0, 340)
        tree.setColumnWidth(1, 80)
        tree.setColumnWidth(2, 90)
        tree.setColumnWidth(3, 220)
        tree.setRootIsDecorated(True)
        tree.setAnimated(True)

        sorted_ranges = sorted(range_detail.keys(), key=lambda x: str(x))

        for range_key in sorted_ranges:
            exacts = range_detail[range_key]
            range_count = sum(len(books) for books in exacts.values())
            range_ratio = (range_count / total_books * 100) if total_books > 0 else 0

            range_item = QTreeWidgetItem([
                range_key,
                f"{range_count}권",
                f"{range_ratio:.1f}%",
                ""
            ])
            font = range_item.font(0)
            font.setBold(True)
            range_item.setFont(0, font)
            tree.addTopLevelItem(range_item)

            sorted_exacts = sorted(
                exacts.items(),
                key=lambda x: float(x[0]) if x[0].replace(".", "", 1).isdigit() else 9999
            )

            for exact, books in sorted_exacts:
                exact_count = len(books)
                exact_ratio = (exact_count / total_books * 100) if total_books > 0 else 0

                exact_item = QTreeWidgetItem([
                    f"  ▶ {exact}",
                    f"{exact_count}권",
                    f"{exact_ratio:.1f}%",
                    ""
                ])
                range_item.addChild(exact_item)

                books_sorted = sorted(books, key=lambda b: b.get("title", ""))
                for book in books_sorted:
                    title = book.get("title", "-")
                    barcode = str(book.get("barcode", ""))
                    author = book.get("author", "")
                    loan_info = ""
                    if barcode in self.loan_status:
                        loan_info = f"대출중 ({self.loan_status[barcode]['name']})"

                    book_item = QTreeWidgetItem([
                        f"    📖 {title}",
                        "",
                        "",
                        f"{barcode}  |  {author}" + (f"  |  {loan_info}" if loan_info else "")
                    ])
                    book_item.setData(0, Qt.ItemDataRole.UserRole, barcode)
                    exact_item.addChild(book_item)

        lay.addWidget(QLabel("• 점대/레벨 클릭 → 펼치기   • 도서 행 더블클릭 → 메인 화면에서 바로 조회"))
        lay.addWidget(tree)

        # ===== 더블클릭 → 메인 화면 조회 + 탭 전환 =====
        def on_item_double_clicked(item, column):
            barcode = item.data(0, Qt.ItemDataRole.UserRole)
            if not barcode:
                return

            # 1) 바코드 넣고 조회
            self.entry_barcode.setText(barcode)
            self.search_book()

            # 2) 대출/반납 탭으로 강제 전환
            self.tabs.setCurrentIndex(0)

            # 3) 다이얼로그 닫고 메인 창 활성화
            dlg.accept()
            self.activateWindow()
            self.entry_student.setFocus()

        tree.itemDoubleClicked.connect(on_item_double_clicked)

        # ===== 엑셀 내보내기 =====
        def export_to_excel():
            file_path, _ = QFileDialog.getSaveFileName(
                dlg,
                "AR 현황 엑셀 저장",
                "AR_Level_Status.xlsx",
                "Excel Files (*.xlsx)"
            )
            if not file_path:
                return

            try:
                rows = []
                for range_key in sorted_ranges:
                    exacts = range_detail[range_key]
                    sorted_exacts = sorted(
                        exacts.items(),
                        key=lambda x: float(x[0]) if x[0].replace(".", "", 1).isdigit() else 9999
                    )
                    for exact, books in sorted_exacts:
                        for book in sorted(books, key=lambda b: b.get("title", "")):
                            barcode = str(book.get("barcode", ""))
                            loan_status = "대출중" if barcode in self.loan_status else "대출가능"
                            borrower = self.loan_status[barcode]["name"] if barcode in self.loan_status else ""
                            rows.append({
                                "AR 점대": range_key,
                                "정확한 AR": exact,
                                "바코드": barcode,
                                "도서명": book.get("title", ""),
                                "저자/출판사": book.get("author", ""),
                                "Lexile": book.get("lexile", ""),
                                "Quiz No": book.get("ar_quiz_no", ""),
                                "대출상태": loan_status,
                                "대출자": borrower,
                            })

                df = pd.DataFrame(rows)
                df.to_excel(file_path, index=False)
                QMessageBox.information(dlg, "성공", f"엑셀 파일이 저장되었습니다.\n{file_path}")
            except Exception as e:
                QMessageBox.critical(dlg, "오류", f"엑셀 저장 실패:\n{e}")

        # ===== 버튼 영역 =====
        btn_layout = QHBoxLayout()

        btn_expand = QPushButton("모두 펼치기")
        btn_expand.clicked.connect(tree.expandAll)

        btn_collapse = QPushButton("모두 접기")
        btn_collapse.clicked.connect(tree.collapseAll)

        btn_excel = QPushButton("📥 엑셀로 내보내기")
        btn_excel.setStyleSheet("background:#38a169;")
        btn_excel.clicked.connect(export_to_excel)

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)

        btn_layout.addWidget(btn_expand)
        btn_layout.addWidget(btn_collapse)
        btn_layout.addWidget(btn_excel)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)

        lay.addLayout(btn_layout)
        dlg.exec()

    def on_add_book_clicked(self):
        if not self.require_admin("신규 도서 등록"):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("신규 도서 등록")
        dlg.resize(400, 350)
        dlg.setStyleSheet("""
            QDialog { background:#1a202c; color:#e2e8f0; }
            QLineEdit { background:#2d3748; color:white; border:1px solid #4a5568; border-radius:4px; padding:8px; }
            QPushButton { background:#3182ce; color:white; border-radius:4px; font-weight:bold; padding:10px; }
        """)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)

        entries = {}
        fields = [
            ("barcode", "바코드 번호 *"),
            ("title", "도서명 *"),
            ("author", "저자 / 출판사"),
            ("ar_level", "AR Level (예: 3.5)"),
            ("lexile", "Lexile (예: 500L)"),
            ("ar_quiz_no", "AR Quiz No"),
        ]

        for key, label in fields:
            lay.addWidget(QLabel(label))
            le = KoreanLineEdit()
            entries[key] = le
            lay.addWidget(le)

        def save_book():
            bc = entries["barcode"].text().strip()
            title = entries["title"].text().strip()
            if not bc or not title:
                QMessageBox.warning(dlg, "입력 오류", "바코드와 도서명은 필수 입력 항목입니다.")
                return

            ar_raw = entries["ar_level"].text().strip()
            ar_val = None
            if ar_raw:
                try:
                    ar_val = float(ar_raw)
                except ValueError:
                    ar_val = ar_raw

            book_data = {
                "barcode": bc,
                "title": title,
                "author": entries["author"].text().strip(),
                "ar_level": ar_val,
                "lexile": entries["lexile"].text().strip(),
                "ar_quiz_no": entries["ar_quiz_no"].text().strip(),
            }

            try:
                db.upsert_books(book_data)
                QMessageBox.information(dlg, "성공", f"'{title}' 도서가 등록되었습니다.")
                self.load_books_cache()
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "오류", f"도서 등록 실패:\n{e}")

        btn = QPushButton("등록 저장")
        btn.clicked.connect(save_book)
        lay.addWidget(btn)
        dlg.exec()

    def on_bulk_add_clicked(self):
        if not self.require_admin("도서 일괄 등록"):
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "도서 엑셀/CSV 파일 선택", "", "Excel Files (*.xlsx *.xls);;CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            if file_path.endswith(".csv"):
                df = pd.read_csv(file_path, dtype=str)
            else:
                df = pd.read_excel(file_path, dtype=str)

            df = df.fillna("")
            records = []
            for _, row in df.iterrows():
                bc = str(row.get("barcode", row.get("바코드", ""))).strip()
                title = str(row.get("title", row.get("도서명", ""))).strip()
                if not bc or not title:
                    continue

                ar_raw = str(
                    row.get("ar_level", row.get("AR", row.get("ar", "")))
                ).strip()
                ar_val = None
                if ar_raw:
                    try:
                        ar_val = float(ar_raw)
                    except ValueError:
                        ar_val = ar_raw

                records.append({
                    "barcode": bc,
                    "title": title,
                    "author": str(
                        row.get("author", row.get("저자", row.get("출판사", "")))
                    ).strip(),
                    "ar_level": ar_val,
                    "lexile": str(
                        row.get("lexile", row.get("Lexile", row.get("lex", "")))
                    ).strip(),
                    "ar_quiz_no": str(
                        row.get(
                            "ar_quiz_no", row.get("QuizNo", row.get("quiz_no", ""))
                        )
                    ).strip(),
                })

            if not records:
                QMessageBox.warning(self, "경고", "유효한 도서 데이터가 없습니다.")
                return

            db.upsert_books(records)
            self.load_books_cache()
            QMessageBox.information(
                self, "성공", f"총 {len(records)}권의 도서가 일괄 등록되었습니다."
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"일괄 등록 중 오류 발생:\n{e}")

    def on_delete_book_clicked(self):
        if not self.require_admin("도서 정보 삭제"):
            return

        bc, ok = QInputDialog.getText(
            self, "도서 삭제", "삭제할 도서의 바코드를 입력하세요:"
        )
        if not ok or not bc.strip():
            return
        bc = bc.strip()

        if bc in self.loan_status:
            QMessageBox.warning(
                self,
                "삭제 불가",
                f"현재 대출 중인 도서('{self.loan_status[bc].get('title', bc)}')는"
                " 삭제할 수 없습니다.\n먼저 반납 처리해 주세요.",
            )
            return

        book = self.books_cache.get(bc)
        title = book.get("title", bc) if book else bc

        reply = QMessageBox.question(
            self,
            "삭제 확인",
            f"정말 다음 도서 정보를 삭제하시겠습니까?\n바코드: [{bc}]\n도서명: {title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            db.delete_book_by_barcode(bc)
            self.load_books_cache()
            QMessageBox.information(self, "성공", "도서가 삭제되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"도서 삭제 실패:\n{e}")

    def export_loan_excel(self):
        if not self.loan_status:
            QMessageBox.warning(self, "알림", "현재 대출 중인 도서가 없습니다.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "엑셀 저장", "current_loans.xlsx", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            data = []
            now = datetime.now()
            for bc, info in self.loan_status.items():
                book = self.books_cache.get(bc, {})
                minutes = (now - info["date"]).total_seconds() / 60
                status = "정상" if minutes <= config.OVERDUE_MINUTES else "연체"
                data.append({
                    "바코드": bc,
                    "도서명": info.get("title") or book.get("title", ""),
                    "저자": book.get("author", ""),
                    "대출자": info["name"],
                    "대출일시": info["date"].strftime("%Y-%m-%d %H:%M:%S"),
                    "상태": status,
                })
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False)
            QMessageBox.information(
                self, "성공", f"파일이 성공적으로 저장되었습니다:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"엑셀 저장 실패:\n{e}")

    def export_logs_excel(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "엑셀 저장", "library_logs.xlsx", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            logs = db.fetch_logs_ordered()
            if not logs:
                QMessageBox.warning(self, "알림", "로그 데이터가 없습니다.")
                return

            df = pd.DataFrame(logs)
            df.to_excel(file_path, index=False)
            QMessageBox.information(
                self, "성공", f"전체 로그 파일이 저장되었습니다:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"로그 저장 실패:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LibraryApp()
    window.show()
    sys.exit(app.exec())
