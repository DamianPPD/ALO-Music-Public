import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QWidget

from audio_library_organizer.ui.theme import style_for_theme
from audio_library_organizer.ui.v0411_theme import style_for_v0411


def test_complete_dark_theme_is_accepted_by_qt():
    app = QApplication.instance() or QApplication([])
    original = app.styleSheet()
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    widget = QWidget()
    try:
        app.setStyleSheet(style_for_theme('dark') + style_for_v0411('dark'))
        widget.show()
        app.processEvents()
        assert not [message for message in messages if 'Could not parse' in message]
    finally:
        widget.close()
        app.setStyleSheet(original)
        qInstallMessageHandler(previous)
