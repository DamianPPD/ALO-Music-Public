"""Scoped geometry for the approved export and creation dialogs."""
from PySide6.QtCore import QSize


def configure_dialog_button(button, *, accent=None, stripe=False, icon_size=18):
    button.setFixedHeight(40)
    button.setIconSize(QSize(icon_size, icon_size))
    background, border = {
        'blue': ('#146dff', '#3886ff'),
        'green': ('#247d59', '#35d893'),
        'magenta': ('#a63879', '#65314f'),
    }.get(accent, ('#222b35', '#455361'))
    left = 'border-left:3px solid #e9a83b;' if stripe else ''
    hover = {'blue': '#287fff', 'green': '#2c8f68', 'magenta': '#b64085'}.get(accent, '#31404d')
    button.setStyleSheet(f'''
        QPushButton {{ background:{background}; color:#e0eaf0; border:1px solid {border};
            border-radius:7px; padding:0 16px; min-height:38px; max-height:38px; font-size:13px; {left} }}
        QPushButton:hover {{ background:{hover}; border-color:#83a5b7; {left} }}
        QPushButton:pressed {{ background:#17232d; border-color:#9bc6dc; {left} }}
        QPushButton:focus {{ border:1px solid #c3e7fa; {left} }}
        QPushButton:disabled {{ background:#263039; color:#82929c; border-color:#34414b;
            {'border-left:3px solid #756546;' if stripe else ''} }}
    ''')
