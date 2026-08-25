# utils.py
from PyQt6.QtWidgets import QLineEdit


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
