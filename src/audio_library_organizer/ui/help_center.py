from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QTextBrowser, QLineEdit
from audio_library_organizer.help_content import HELP_TOPICS
from audio_library_organizer.help_content_en import HELP_TOPICS_EN
from audio_library_organizer.ui.i18n import apply_static_language


class HelpCenter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._language = 'pl'
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Szukaj w pomocy…')
        self.topics = QListWidget()
        left.addWidget(self.search)
        left.addWidget(self.topics, 1)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        root.addLayout(left, 1)
        root.addWidget(self.browser, 3)
        self.search.textChanged.connect(self._reload)
        self.topics.currentTextChanged.connect(self._show)
        self._reload()

    def set_language(self, language: str) -> None:
        selected = self._selected_topic()
        self._language = 'en' if language == 'en' else 'pl'
        self.setProperty('_alo_language', self._language)
        apply_static_language(self.search, self._language)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._reload()
        if selected:
            self.show_topic(selected)

    def _selected_topic(self) -> str | None:
        item = self.topics.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _title(self, topic: str) -> str:
        return HELP_TOPICS_EN[topic][0] if self._language == 'en' else topic

    def _reload(self):
        q = self.search.text().casefold().strip()
        current = self._selected_topic()
        self.topics.clear()
        for title, body in HELP_TOPICS.items():
            visible_title = self._title(title)
            visible_body = HELP_TOPICS_EN[title][1] if self._language == 'en' else body
            if not q or q in visible_title.casefold() or q in visible_body.casefold():
                self.topics.addItem(visible_title)
                self.topics.item(self.topics.count() - 1).setData(Qt.ItemDataRole.UserRole, title)
        if self.topics.count():
            if current:
                matches = [self.topics.item(i) for i in range(self.topics.count()) if self.topics.item(i).data(Qt.ItemDataRole.UserRole) == current]
                if matches:
                    self.topics.setCurrentItem(matches[0])
                    return
            self.topics.setCurrentRow(0)

    def show_topic(self, title: str):
        self.search.clear()
        matches = [self.topics.item(i) for i in range(self.topics.count()) if self.topics.item(i).data(Qt.ItemDataRole.UserRole) == title]
        if matches:
            self.topics.setCurrentItem(matches[0])
            self._show(self._title(title))

    def _show(self, title: str):
        if title:
            topic = self._selected_topic()
            if topic is None:
                return
            body = HELP_TOPICS_EN[topic][1] if self._language == 'en' else HELP_TOPICS[topic]
            self.browser.setHtml(f'''<style>
                body{{font-family:Segoe UI;line-height:1.55;color:#edf3f8;background:#11171e;margin:14px 18px;}}
                h1{{font-size:24px;margin:0 0 14px 0;color:#f5f8fb;}}
                h2{{font-size:18px;color:#dce9f3;margin:18px 0 8px 0;}}
                h3{{font-size:15px;color:#8fe9ad;margin:18px 0 7px 0;}}
                p{{margin:7px 0;}}
                ol,ul{{margin:7px 0 12px 24px;}}
                li{{margin:5px 0;}}
                code{{background:#1b202a;padding:2px 5px;border-radius:4px;}}
                a{{color:#68a5ff;}}
                .help-card{{background:#171f28;border:1px solid #2b3b4c;border-radius:8px;padding:10px 12px;margin:9px 0;}}
                .important{{background:#2b2213;border:1px solid #6e5324;border-radius:8px;padding:10px 12px;margin:10px 0;color:#ffd99a;}}
                .ok{{background:#13271b;border:1px solid #2f6344;border-radius:8px;padding:10px 12px;margin:10px 0;color:#9df0b7;}}
            </style><h1>{title}</h1>{body.strip()}''')
