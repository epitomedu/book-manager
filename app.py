import sys
import os
import csv
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
from supabase import Client, create_client

# Supabase 설정 정보
SUPABASE_URL = "https://ldpbwvdpltpdjazqviwa.supabase.co"
SUPABASE_KEY = "sb_publishable_nXwWJyL3ZzBN_nfTuQbieA_NqVkkJ6n"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class KoreanLineEdit(QLineEdit):
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
        self.loan_status = {}
        self.current_book_data = None
        self.MAX_LOAN = 4
        self.OVERDUE_MINUTES = 1   # 테스트용 연체 기준 (1분)

        self.init_ui()
        self.load_loan_logs_from_supabase()
        self.update_status_bar()

        # 실시간 상태 갱신을 위한 타이머 (1초 간격)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start()

    def load_loan_logs_from_supabase(self):
        print("[정보] Supabase에서 대출 기록을 불러오는 중...")
        try:
            response = supabase.table("logs").select("*").execute()
            rows = response.data
            
            self.loan_status.clear()
            for row in rows:
                barcode = row.get("barcode")
                student_name = row.get("student_name")
                action = row.get("action")
                created_at_str = row.get("date")
                
                try:
                    if created_at_str:
                        loan_date = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00")).replace(tzinfo=None)
                    else:
                        loan_date = datetime.now()
                except:
                    loan_date = datetime.now()

                if action == "RENT":
                    self.loan_status[barcode] = {"name": student_name, "date": loan_date}
                elif action == "RETURN" and barcode in self.loan_status:
                    del self.loan_status[barcode]
            
            print(f"[성공] 대출 기록 복원 완료 (현재 대출 중인 도서: {len(self.loan_status)}권)")
        except Exception as e:
            print(f"[오류] Supabase 로그 로드 실패: {e}")

    def get_book_info_from_supabase(self, barcode):
        try:
            response = supabase.table("books").select("*").eq("barcode", barcode).execute()
            if response.data and len(response.data) > 0:
                book = response.data[0]
                return {
                    'Barcode': book.get('barcode'),
                    'Title': book.get('title'),
                    'Author': book.get('author'),
                    'AR Level': book.get('ar_level'),
                    'Lexile': book.get('lexile'),
                    'Points': book.get('points'),
                    'AR Quiz No': book.get('ar_quiz_no', '')
                }
        except Exception as e:
            print(f"[오류] 도서 조회 중 에러: {e}")
        return None

    def force_commit_ime(self):
        focused = QApplication.focusWidget()
        if focused and isinstance(focused, KoreanLineEdit):
            focused.clearFocus()
            QApplication.processEvents()
            focused.setFocus()
            QApplication.processEvents()

    def get_student_id(self):
        name = self.entry_student.text().strip()
        phone = self.entry_phone.text().strip()
        if not name or not phone:
            return None
        return f"{name} ({phone})"

    def get_student_loan_count(self, student_id):
        return sum(1 for info in self.loan_status.values() if info["name"] == student_id)

    def has_borrowed_before(self, student_id, barcode):
        try:
            response = supabase.table("logs").select("*").eq("student_name", student_id).eq("barcode", barcode).eq("action", "RENT").execute()
            if response.data and len(response.data) > 0:
                return True
        except:
            pass
        return False

    def get_overdue_count(self):
        count = 0
        for info in self.loan_status.values():
            minutes = (datetime.now() - info["date"]).total_seconds() / 60
            if minutes > self.OVERDUE_MINUTES:
                count += 1
        return count

    def update_status_bar(self):
        total = len(self.loan_status)
        overdue = self.get_overdue_count()
        self.lbl_bottom_status.setText(
            f"📚 현재 대출 중: {total}권    |    ⚠️ 연체: {overdue}권    |    최대 대출: {self.MAX_LOAN}권/인"
        )
        if overdue > 0:
            self.lbl_bottom_status.setStyleSheet(
                "background-color: #742a2a; color: #fed7d7; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;"
            )
        else:
            self.lbl_bottom_status.setStyleSheet(
                "background-color: #2d3748; color: #a0aec0; font-weight: bold; font-size: 13px; padding: 10px; border-radius: 6px;"
            )

    def init_ui(self):
        self.setWindowTitle("📚 Epitome Edu Library System")
        self.resize(580, 720)
        self.setStyleSheet("""
            QWidget { background-color: #1a202c; color: #e2e8f0; font-family: 'Apple SD Gothic Neo', '맑은 고딕', sans-serif; }
            QLineEdit { background-color: #2d3748; color: white; border: 1px solid #4a5568; border-radius: 6px; padding: 8px; font-size: 14px; }
            QPushButton { background-color: #3182ce; color: white; border-radius: 6px; font-weight: bold; font-size: 13px; padding: 10px; }
            QPushButton:hover { background-color: #2b6cb0; }
            QLabel { font-size: 13px; }
            QTabWidget::pane { border: 1px solid #4a5568; border-radius: 8px; background: #1a202c; }
            QTabBar::tab { background: #2d3748; color: #a0aec0; padding: 10px 18px; margin-right: 4px; border-top-left-radius: 8px; border-top-right-radius: 8px; font-weight: bold; font-size: 13px; }
            QTabBar::tab:selected { background: #3182ce; color: white; }
            QGroupBox { border: 1px solid #4a5568; border-radius: 8px; margin-top: 12px; font-weight: bold; color: #90cdf4; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # 탭 1: 대출/반납
        tab_loan = QWidget()
        layout_loan = QVBoxLayout(tab_loan)
        layout_loan.setSpacing(12)

        card_bc = QGroupBox("📷 바코드 스캔")
        vbox_bc = QVBoxLayout()
        hbox_bc = QHBoxLayout()
        self.entry_barcode = KoreanLineEdit("바코드 입력 후 Enter")
        self.entry_barcode.returnPressed.connect(self.on_barcode_enter)
        hbox_bc.addWidget(self.entry_barcode)
        btn_bc_ok = QPushButton("확인")
        btn_bc_ok.clicked.connect(self.safe_search)
        hbox_bc.addWidget(btn_bc_ok)
        btn_bc_clear = QPushButton("지우기")
        btn_bc_clear.setStyleSheet("background-color: #4a5568;")
        btn_bc_clear.clicked.connect(lambda: self.entry_barcode.clear())
        hbox_bc.addWidget(btn_bc_clear)
        vbox_bc.addLayout(hbox_bc)
        card_bc.setLayout(vbox_bc)
        layout_loan.addWidget(card_bc)

        card_st = QGroupBox("👤 대여자 정보")
        vbox_st = QVBoxLayout()
        hbox_name = QHBoxLayout()
        hbox_name.addWidget(QLabel("이름:"))
        self.entry_student = KoreanLineEdit("학생 이름")
        self.entry_student.returnPressed.connect(self.on_student_enter)
        hbox_name.addWidget(self.entry_student)
        vbox_st.addLayout(hbox_name)

        hbox_phone = QHBoxLayout()
        hbox_phone.addWidget(QLabel("핸드폰 끝 4자리:"))
        self.entry_phone = KoreanLineEdit("1234")
        self.entry_phone.setMaxLength(4)
        self.entry_phone.setValidator(QIntValidator(0, 9999))
        self.entry_phone.returnPressed.connect(self.on_student_enter)
        hbox_phone.addWidget(self.entry_phone)
        vbox_st.addLayout(hbox_phone)

        hbox_st_btn = QHBoxLayout()
        btn_st_ok = QPushButton("확인")
        btn_st_ok.clicked.connect(self.safe_check)
        hbox_st_btn.addWidget(btn_st_ok)
        btn_st_clear = QPushButton("지우기")
        btn_st_clear.setStyleSheet("background-color: #4a5568;")
        btn_st_clear.clicked.connect(self.clear_student_fields)
        hbox_st_btn.addWidget(btn_st_clear)
        vbox_st.addLayout(hbox_st_btn)
        card_st.setLayout(vbox_st)
        layout_loan.addWidget(card_st)

        card_info = QGroupBox("📖 도서 정보")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)

        def add_row(r, text):
            k = QLabel(text)
            k.setStyleSheet("color: #a0aec0; font-weight: bold;")
            v = QLabel("-")
            v.setStyleSheet("font-weight: bold; font-size: 13px;")
            grid.addWidget(k, r, 0)
            grid.addWidget(v, r, 1)
            return v

        self.lbl_title = add_row(0, "제      목 :")
        self.lbl_title.setStyleSheet("color: #63b3ed; font-weight: bold;")
        self.lbl_author = add_row(1, "저      자 :")
        self.lbl_ar = add_row(2, "AR Level :")
        self.lbl_lexile = add_row(3, "Lexile    :")
        self.lbl_quiz = add_row(4, "Quiz No  :")
        self.lbl_barcode = add_row(5, "바 코 드  :")
        self.lbl_loan = add_row(6, "대출 상태 :")
        self.lbl_loan.setStyleSheet("color: #48bb78; font-weight: bold;")
        card_info.setLayout(grid)
        layout_loan.addWidget(card_info)

        hbox_btn = QHBoxLayout()
        btn_loan = QPushButton("📥 대출하기")
        btn_loan.setStyleSheet("background-color: #2b6cb0; font-size: 15px; padding: 12px;")
        btn_loan.clicked.connect(lambda: self.safe_process("RENT"))
        hbox_btn.addWidget(btn_loan)

        btn_return = QPushButton("📤 반납하기")
        btn_return.setStyleSheet("background-color: #2f855a; font-size: 15px; padding: 12px;")
        btn_return.clicked.connect(lambda: self.safe_process("RETURN"))
        hbox_btn.addWidget(btn_return)
        layout_loan.addLayout(hbox_btn)

        self.lbl_status = QLabel("준비됨")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-weight: bold; color: #fc8181; font-size: 13px; padding: 6px;")
        layout_loan.addWidget(self.lbl_status)

        layout_loan.addStretch()
        tabs.addTab(tab_loan, "📋 대출/반납")

        # 탭 2: 현황 조회
        tab_status = QWidget()
        layout_status = QVBoxLayout(tab_status)
        layout_status.setSpacing(14)

        btn_status = QPushButton("📋 전체 대출 현황 보기")
        btn_status.setStyleSheet("background-color: #805ad5; font-size: 15px; padding: 14px;")
        btn_status.clicked.connect(self.show_loan_status)
        layout_status.addWidget(btn_status)

        btn_overdue = QPushButton("⚠️ 연체자 목록 보기")
        btn_overdue.setStyleSheet("background-color: #e53e3e; font-size: 15px; padding: 14px;")
        btn_overdue.clicked.connect(self.show_overdue_list)
        layout_status.addWidget(btn_overdue)

        btn_ar_status = QPushButton("📊 AR Level별 대여 가능 현황")
        btn_ar_status.setStyleSheet("background-color: #319795; font-size: 15px; padding: 14px;")
        btn_ar_status.clicked.connect(self.show_ar_level_status)
        layout_status.addWidget(btn_ar_status)

        layout_status.addStretch()
        tabs.addTab(tab_status, "📊 현황 조회")

        # 탭 3: 도서 관리
        tab_manage = QWidget()
        layout_manage = QVBoxLayout(tab_manage)
        layout_manage.setSpacing(14)

        btn_add_book = QPushButton("➕ 새 도서 등록 (Supabase)")
        btn_add_book.setStyleSheet("background-color: #dd6b20; font-size: 15px; padding: 14px;")
        btn_add_book.clicked.connect(self.show_add_book_dialog)
        layout_manage.addWidget(btn_add_book)

        btn_del_book = QPushButton("🗑️ 도서 삭제 (Supabase)")
        btn_del_book.setStyleSheet("background-color: #9b2c2c; font-size: 15px; padding: 14px;")
        btn_del_book.clicked.connect(self.show_delete_book_dialog)
        layout_manage.addWidget(btn_del_book)

        layout_manage.addStretch()
        tabs.addTab(tab_manage, "📚 도서 관리")

        # 탭 4: 엑셀 저장
        tab_excel = QWidget()
        layout_excel = QVBoxLayout(tab_excel)
        layout_excel.setSpacing(14)

        btn_excel_status = QPushButton("📊 대출 현황 엑셀 저장")
        btn_excel_status.setStyleSheet("background-color: #2b6cb0; font-size: 15px; padding: 14px;")
        btn_excel_status.clicked.connect(self.export_loan_status_excel)
        layout_excel.addWidget(btn_excel_status)

        btn_excel_log = QPushButton("📜 전체 로그 엑셀 저장")
        btn_excel_log.setStyleSheet("background-color: #4a5568; font-size: 15px; padding: 14px;")
        btn_excel_log.clicked.connect(self.export_all_logs_excel)
        layout_excel.addWidget(btn_excel_log)

        layout_excel.addStretch()
        tabs.addTab(tab_excel, "📥 엑셀 저장")

        main_layout.addWidget(tabs)

        self.lbl_bottom_status = QLabel()
        self.lbl_bottom_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_bottom_status)

        self.setLayout(main_layout)
        self.entry_barcode.setFocus()

    def clear_student_fields(self):
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
        book = self.get_book_info_from_supabase(code)
        if book:
            self.current_book_data = book
            barcode = book.get('Barcode', '')
            self.lbl_title.setText(book.get('Title', '-'))
            self.lbl_author.setText(book.get('Author', '-'))
            self.lbl_ar.setText(str(book.get('AR Level', '-')))
            self.lbl_lexile.setText(str(book.get('Lexile', '-')))
            self.lbl_quiz.setText(str(book.get('AR Quiz No', '-')))
            self.lbl_barcode.setText(barcode)

            if barcode in self.loan_status:
                info = self.loan_status[barcode]
                self.lbl_loan.setText(f"대출 중 ({info['name']})")
                self.lbl_loan.setStyleSheet("color: #fc8181; font-weight: bold;")
                self.lbl_status.setText(f"[주의] 현재 '{info['name']}'님이 대출 중입니다.")
                self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
            else:
                self.lbl_loan.setText("대출 가능")
                self.lbl_loan.setStyleSheet("color: #48bb78; font-weight: bold;")
                self.lbl_status.setText("도서 조회 성공. 이름과 핸드폰 끝 4자리를 입력하세요.")
                self.lbl_status.setStyleSheet("color: #63b3ed; font-weight: bold;")
        else:
            self.current_book_data = None
            self.lbl_title.setText("등록되지 않은 도서입니다.")
            self.lbl_author.setText("-")
            self.lbl_ar.setText("-")
            self.lbl_lexile.setText("-")
            self.lbl_quiz.setText("-")
            self.lbl_barcode.setText(code)
            self.lbl_loan.setText("-")
            self.lbl_status.setText("[오류] Supabase에 없는 바코드입니다.")
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
        QTimer.singleShot(50, lambda: self.entry_student.setFocus())

    def check_student(self):
        student_id = self.get_student_id()
        if not student_id:
            self.lbl_status.setText("[경고] 이름과 핸드폰 끝 4자리를 모두 입력하세요!")
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
            return

        count = self.get_student_loan_count(student_id)
        overdue_list = []
        titles = []

        for b, info in self.loan_status.items():
            if info["name"] == student_id:
                book_info = self.get_book_info_from_supabase(b)
                title = book_info.get('Title', '제목없음') if book_info else f"바코드:{b}"
                titles.append(title)
                minutes = (datetime.now() - info["date"]).total_seconds() / 60
                if minutes > self.OVERDUE_MINUTES:
                    overdue_list.append(f"{title} ({int(minutes)}분 연체)")

        msg = f"'{student_id}'님 현재 대출: {count}/{self.MAX_LOAN}권"
        if titles:
            msg += f"\n도서: {', '.join(titles)}"
        if overdue_list:
            msg += f"\n⚠️ 연체 도서: {', '.join(overdue_list)}"
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
        else:
            self.lbl_status.setStyleSheet("color: #48bb78; font-weight: bold;")

        self.lbl_status.setText(msg)

    def process_action(self, action_type):
        if not self.current_book_data:
            self.lbl_status.setText("[경고] 먼저 도서를 조회해주세요!")
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
            return

        student_id = self.get_student_id()
        if not student_id:
            self.lbl_status.setText("[경고] 이름과 핸드폰 끝 4자리를 모두 입력하세요!")
            self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
            return

        barcode = self.current_book_data.get('Barcode', '')
        title = self.current_book_data.get('Title', '')
        author = self.current_book_data.get('Author', '')
        ar_level = str(self.current_book_data.get('AR Level', ''))

        if action_type == "RENT":
            current_count = self.get_student_loan_count(student_id)
            if current_count >= self.MAX_LOAN:
                QMessageBox.warning(self, "대출 제한", f"'{student_id}'님은 이미 {current_count}권을 대출 중입니다.\n최대 {self.MAX_LOAN}권까지 가능합니다.")
                return

            if barcode in self.loan_status:
                self.lbl_status.setText(f"[오류] 이미 '{self.loan_status[barcode]['name']}'님이 대출 중!")
                self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
                return

            if self.has_borrowed_before(student_id, barcode):
                reply = QMessageBox.information(
                    self, "이전 대여 안내",
                    f"'{student_id}'님은 이전에 이 책을 대여한 적이 있습니다.\n그래도 대출하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

        else: # RETURN
            if barcode not in self.loan_status:
                self.lbl_status.setText("[오류] 대출 기록이 없는 도서입니다!")
                self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
                return
            if self.loan_status[barcode]["name"] != student_id:
                self.lbl_status.setText(f"[오류] '{self.loan_status[barcode]['name']}'님이 대출한 책입니다!")
                self.lbl_status.setStyleSheet("color: #fc8181; font-weight: bold;")
                return

        try:
            current_time_str = datetime.now().isoformat()
            log_data = {
                "date": current_time_str,
                "barcode": barcode,
                "student_name": student_id,
                "action": action_type,
                "title": title,
                "author": author,
                "ar_level": ar_level
            }
            supabase.table("logs").insert(log_data).execute()

            if action_type == "RENT":
                self.loan_status[barcode] = {"name": student_id, "date": datetime.now()}
                self.lbl_loan.setText(f"대출 중 ({student_id})")
                self.lbl_loan.setStyleSheet("color: #fc8181; font-weight: bold;")
                action_label = "대출"
            else:
                del self.loan_status[barcode]
                self.lbl_loan.setText("대출 가능 (반납됨)")
                self.lbl_loan.setStyleSheet("color: #48bb78; font-weight: bold;")
                action_label = "반납"

            self.lbl_status.setText(f"[{title}] 도서 [{action_label}] 완료! ({student_id})")
            self.lbl_status.setStyleSheet("color: #63b3ed; font-weight: bold;")

            QMessageBox.information(self, "성공", f"[{title}] 도서가 정상적으로 {action_label} 처리되었습니다.\n대여자: {student_id}")

            self.entry_barcode.clear()
            self.clear_student_fields()
            self.entry_barcode.setFocus()
            self.update_status_bar()

        except Exception as e:
            QMessageBox.critical(self, "처리 오류", f"대여/반납 처리 중 오류가 발생했습니다:\n{str(e)}")

    def show_loan_status(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"현재 대출 현황 (총 {len(self.loan_status)}권)")
        dialog.resize(1050, 480)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a202c; color: #e2e8f0; }
            QTableWidget { background-color: #2d3748; color: white; gridline-color: #4a5568; font-size: 13px; }
            QHeaderView::section { background-color: #4a5568; color: white; font-weight: bold; padding: 6px; }
            QPushButton { background-color: #3182ce; color: white; border-radius: 4px; font-weight: bold; padding: 6px 10px; }
        """)

        layout = QVBoxLayout()
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels(["바코드", "제목", "저자", "AR Level", "대출자", "대출일", "상태", "관리"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSortingEnabled(False)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        rows_data = []
        for barcode, info in list(self.loan_status.items()):
            book = self.get_book_info_from_supabase(barcode)
            if book:
                title = book.get('Title', '')
                author = book.get('Author', '')
                ar_level = str(book.get('AR Level', ''))
            else:
                title = "(정보 없음)"
                author = ""
                ar_level = ""

            minutes = (datetime.now() - info["date"]).total_seconds() / 60
            status = f"{int(minutes)}분 경과"
            if minutes > self.OVERDUE_MINUTES:
                status = f"⚠️ 연체 {int(minutes - self.OVERDUE_MINUTES)}분"

            rows_data.append([barcode, title, author, ar_level, info["name"], info["date"].strftime('%Y-%m-%d %H:%M'), status])

        table.setRowCount(len(rows_data))
        for i, row_data in enumerate(rows_data):
            for j, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                
                # 셀 내용 가운데 정렬 추가
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if j == 6 and "연체" in str(value):
                    item.setForeground(QBrush(QColor("#fc8181")))
                table.setItem(i, j, item)

            barcode_val = row_data[0]
            student_val = row_data[4]
            btn_return_item = QPushButton("반납처리")
            btn_return_item.setStyleSheet("background-color: #2f855a; font-size: 11px; padding: 4px;")
            
            def make_return_handler(b_code, s_name, dlg):
                return lambda: self.return_from_status_dialog(b_code, s_name, dlg)

            btn_return_item.clicked.connect(make_return_handler(barcode_val, student_val, dialog))
            table.setCellWidget(i, 7, btn_return_item)

        layout.addWidget(table)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.setLayout(layout)
        dialog.exec()

    def return_from_status_dialog(self, barcode, student_id, dialog):
        reply = QMessageBox.question(
            dialog, "반납 확인",
            f"바코드 [{barcode}] 도서를 반납 처리하시겠습니까?\n대여자: {student_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return

        book_info = self.get_book_info_from_supabase(barcode)
        title = book_info.get('Title', '') if book_info else ''
        author = book_info.get('Author', '') if book_info else ''
        ar_level = str(book_info.get('AR Level', '')) if book_info else ''

        try:
            current_time_str = datetime.now().isoformat()
            log_data = {
                "date": current_time_str,
                "barcode": barcode,
                "student_name": student_id,
                "action": "RETURN",
                "title": title,
                "author": author,
                "ar_level": ar_level
            }
            supabase.table("logs").insert(log_data).execute()

            if barcode in self.loan_status:
                del self.loan_status[barcode]

            QMessageBox.information(dialog, "성공", "정상적으로 반납 처리되었습니다.")
            dialog.accept()
            self.update_status_bar()
        except Exception as e:
            QMessageBox.critical(dialog, "오류", f"반납 처리 중 오류 발생:\n{str(e)}")

    def show_overdue_list(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("연체자 목록")
        dialog.resize(950, 450)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a202c; color: #e2e8f0; }
            QTableWidget { background-color: #2d3748; color: white; gridline-color: #4a5568; font-size: 13px; }
            QHeaderView::section { background-color: #e53e3e; color: white; font-weight: bold; padding: 6px; }
            QPushButton { background-color: #3182ce; color: white; border-radius: 4px; font-weight: bold; padding: 8px; }
        """)

        layout = QVBoxLayout()
        overdue_items = []
        for barcode, info in self.loan_status.items():
            minutes = (datetime.now() - info["date"]).total_seconds() / 60
            if minutes > self.OVERDUE_MINUTES:
                overdue_items.append((barcode, info, minutes))

        if not overdue_items:
            lbl = QLabel("현재 연체된 도서가 없습니다.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 16px; color: #68d391; padding: 40px;")
            layout.addWidget(lbl)
            btn_close = QPushButton("닫기")
            btn_close.clicked.connect(dialog.accept)
            layout.addWidget(btn_close)
            dialog.setLayout(layout)
            dialog.exec()
            return

        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["바코드", "제목", "저자", "AR Level", "대출자", "대출일", "연체시간"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        table.setRowCount(len(overdue_items))
        for i, (barcode, info, minutes) in enumerate(overdue_items):
            book = self.get_book_info_from_supabase(barcode)
            title = book.get('Title', '') if book else "(정보 없음)"
            author = book.get('Author', '') if book else ""
            ar_level = str(book.get('AR Level', '')) if book else ""

            row_data = [
                barcode, title, author, ar_level,
                info["name"], info["date"].strftime('%Y-%m-%d %H:%M'),
                f"{int(minutes - self.OVERDUE_MINUTES)}분 연체"
            ]

            for j, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                
                # 셀 내용 가운데 정렬 추가
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if j == 6:
                    item.setForeground(QBrush(QColor("#fc8181")))
                table.setItem(i, j, item)

        layout.addWidget(table)
        lbl_count = QLabel(f"총 연체 도서: {len(overdue_items)}권")
        lbl_count.setStyleSheet("font-weight: bold; color: #fc8181; font-size: 14px;")
        layout.addWidget(lbl_count)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.setLayout(layout)
        dialog.exec()

    def show_ar_level_status(self):
        """AR Level별 대여 가능/현황 조회 팝업 (0.1 단위 세분화 및 가운데 정렬 적용)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("AR Level별 상세 도서 및 대여 현황")
        dialog.resize(750, 500)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a202c; color: #e2e8f0; }
            QTableWidget { background-color: #2d3748; color: white; gridline-color: #4a5568; font-size: 13px; }
            QHeaderView::section { background-color: #319795; color: white; font-weight: bold; padding: 6px; }
            QPushButton { background-color: #3182ce; color: white; border-radius: 4px; font-weight: bold; padding: 8px; }
        """)

        layout = QVBoxLayout()
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["AR Level 범위", "총 보유 도서 수", "대출 중", "대출 가능"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        try:
            res = supabase.table("books").select("ar_level, barcode").execute()
            books = res.data
            
            # 0.1 단위별로 딱 떨어지게 그룹화 (예: 1.0, 1.1, 1.2 ...)
            ranges = defaultdict(lambda: {"total": 0, "rented": 0})
            
            for b in books:
                try:
                    ar = float(b.get('ar_level', 0))
                except:
                    ar = 0.0
                
                floor_val = int(ar * 10) / 10.0
                key = f"{floor_val:.1f}"
                
                ranges[key]["total"] += 1
                if b.get('barcode') in self.loan_status:
                    ranges[key]["rented"] += 1

            sorted_keys = sorted(ranges.keys(), key=lambda x: float(x))
            table.setRowCount(len(sorted_keys))

            for i, k in enumerate(sorted_keys):
                total = ranges[k]["total"]
                rented = ranges[k]["rented"]
                available = total - rented

                row_vals = [k, f"{total}권", f"{rented}권", f"{available}권"]
                for j, val in enumerate(row_vals):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                    
                    # 셀 내용 가운데 정렬 추가
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    if j == 3:
                        item.setForeground(QBrush(QColor("#68d391" if available > 0 else "#fc8181")))
                    table.setItem(i, j, item)

        except Exception as e:
            print(f"[오류] AR 통계 조회 실패: {e}")

        layout.addWidget(table)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.setLayout(layout)
        dialog.exec()

    def show_add_book_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("새 도서 등록 (Supabase)")
        dialog.resize(450, 420)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a202c; color: #e2e8f0; }
            QLineEdit { background-color: #2d3748; color: white; border: 1px solid #4a5568; border-radius: 4px; padding: 8px; font-size: 14px; }
            QLabel { font-size: 13px; font-weight: bold; }
            QPushButton { background-color: #3182ce; color: white; border-radius: 4px; font-weight: bold; padding: 10px; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        layout.addWidget(QLabel("바코드"))
        entry_barcode = KoreanLineEdit("바코드 스캔 또는 입력")
        layout.addWidget(entry_barcode)

        layout.addWidget(QLabel("제목"))
        entry_title = KoreanLineEdit("책 제목")
        layout.addWidget(entry_title)

        layout.addWidget(QLabel("저자"))
        entry_author = KoreanLineEdit("저자 이름")
        layout.addWidget(entry_author)

        layout.addWidget(QLabel("AR Level (예: 2.3)"))
        entry_ar = KoreanLineEdit("2.3")
        layout.addWidget(entry_ar)

        layout.addWidget(QLabel("Lexile (선택)"))
        entry_lexile = KoreanLineEdit("450L")
        layout.addWidget(entry_lexile)

        layout.addWidget(QLabel("AR Quiz No (선택)"))
        entry_quiz = KoreanLineEdit("퀴즈 번호")
        layout.addWidget(entry_quiz)

        hbox = QHBoxLayout()
        btn_save = QPushButton("저장")
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background-color: #4a5568;")
        hbox.addWidget(btn_save)
        hbox.addWidget(btn_cancel)
        layout.addLayout(hbox)

        dialog.setLayout(layout)
        entry_barcode.setFocus()

        def save_book():
            barcode = entry_barcode.text().strip()
            title = entry_title.text().strip()
            author = entry_author.text().strip()
            ar_level = entry_ar.text().strip()
            lexile = entry_lexile.text().strip()
            quiz = entry_quiz.text().strip()

            if not barcode or not title or not author or not ar_level:
                QMessageBox.warning(dialog, "입력 오류", "바코드, 제목, 저자, AR Level은 필수입니다.")
                return

            try:
                new_data = {
                    'barcode': barcode,
                    'title': title,
                    'author': author,
                    'ar_level': float(ar_level) if ar_level else 0.0,
                    'lexile': lexile,
                    'ar_quiz_no': quiz
                }
                supabase.table("books").insert(new_data).execute()
                QMessageBox.information(dialog, "등록 완료", f"새 도서가 Supabase에 등록되었습니다!\n\n제목: {title}\n바코드: {barcode}")
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(dialog, "저장 오류", f"도서 등록 중 오류가 발생했습니다:\n{str(e)}")

        btn_save.clicked.connect(save_book)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def show_delete_book_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("도서 삭제 (Supabase)")
        dialog.resize(400, 220)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a202c; color: #e2e8f0; }
            QLineEdit { background-color: #2d3748; color: white; border: 1px solid #4a5568; border-radius: 4px; padding: 8px; font-size: 14px; }
            QLabel { font-size: 13px; font-weight: bold; }
            QPushButton { background-color: #9b2c2c; color: white; border-radius: 4px; font-weight: bold; padding: 10px; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        layout.addWidget(QLabel("삭제할 도서 바코드 입력"))
        entry_barcode = KoreanLineEdit("바코드 스캔 또는 입력")
        layout.addWidget(entry_barcode)

        hbox = QHBoxLayout()
        btn_delete = QPushButton("삭제하기")
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background-color: #4a5568;")
        hbox.addWidget(btn_delete)
        hbox.addWidget(btn_cancel)
        layout.addLayout(hbox)

        dialog.setLayout(layout)
        entry_barcode.setFocus()

        def delete_book():
            barcode = entry_barcode.text().strip()
            if not barcode:
                QMessageBox.warning(dialog, "입력 오류", "바코드를 입력해주세요.")
                return

            book = self.get_book_info_from_supabase(barcode)
            if not book:
                QMessageBox.warning(dialog, "오류", f"바코드 [{barcode}]에 해당하는 도서를 찾을 수 없습니다.")
                return

            title = book.get('Title', '')
            reply = QMessageBox.question(
                dialog, "삭제 확인",
                f"정말 다음 도서를 삭제하시겠습니까?\n\n제목: {title}\n바코드: {barcode}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

            try:
                supabase.table("books").delete().eq("barcode", barcode).execute()
                QMessageBox.information(dialog, "삭제 완료", f"도서가 성공적으로 삭제되었습니다.\n제목: {title}")
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(dialog, "삭제 오류", f"도서 삭제 중 오류가 발생했습니다:\n{str(e)}")

        btn_delete.clicked.connect(delete_book)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def export_loan_status_excel(self):
        """현재 대출 현황을 엑셀 파일로 저장"""
        if not self.loan_status:
            QMessageBox.information(self, "알림", "현재 대출 중인 도서가 없습니다.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "대출 현황 엑셀 저장", "loan_status.xlsx", "Excel Files (*.xlsx);;All Files (*)")
        if not file_path:
            return

        try:
            data = []
            for barcode, info in self.loan_status.items():
                book = self.get_book_info_from_supabase(barcode)
                title = book.get('Title', '') if book else ''
                author = book.get('Author', '') if book else ''
                ar = book.get('AR Level', '') if book else ''
                data.append({
                    "바코드": barcode,
                    "제목": title,
                    "저자": author,
                    "AR Level": ar,
                    "대출자": info["name"],
                    "대출일시": info["date"].strftime('%Y-%m-%d %H:%M')
                })
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False)
            QMessageBox.information(self, "성공", f"대출 현황이 성공적으로 저장되었습니다.\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"엑셀 저장 중 오류 발생:\n{str(e)}")

    def export_all_logs_excel(self):
        """전체 대출/반납 로그를 엑셀 파일로 저장"""
        file_path, _ = QFileDialog.getSaveFileName(self, "전체 로그 엑셀 저장", "all_logs.xlsx", "Excel Files (*.xlsx);;All Files (*)")
        if not file_path:
            return

        try:
            res = supabase.table("logs").select("*").execute()
            rows = res.data
            if not rows:
                QMessageBox.information(self, "알림", "저장할 로그 데이터가 없습니다.")
                return

            df = pd.DataFrame(rows)
            df.to_excel(file_path, index=False)
            QMessageBox.information(self, "성공", f"전체 로그가 성공적으로 저장되었습니다.\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"엑셀 저장 중 오류 발생:\n{str(e)}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LibraryApp()
    window.show()
    sys.exit(app.exec())
