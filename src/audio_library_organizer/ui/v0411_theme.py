from __future__ import annotations

DARK_OVERRIDE = r"""
QFrame#OperationFrame { background:#111b24; border:1px solid #30404f; border-left:5px solid #596675; border-bottom:3px solid #2f7f8d; border-radius:8px; }
QFrame#OperationFrame[operationKind="scan"] { background:#102239; border:1px solid #284b73; border-left:6px solid #5ca3ff; border-bottom:3px solid #5ca3ff; }
QFrame#OperationFrame[operationKind="online"] { background:#201936; border:1px solid #4b3f70; border-left:6px solid #a77dff; border-bottom:3px solid #a77dff; }
QFrame#OperationFrame[operationKind="review"] { background:#2b2011; border:1px solid #6b4d22; border-left:6px solid #ffb84d; border-bottom:3px solid #ffb84d; }
QFrame#OperationFrame[operationKind="export"] { background:#10272a; border:1px solid #285a61; border-left:6px solid #49d6cf; border-bottom:3px solid #49d6cf; }
QFrame#OperationFrame[operationKind="done"] { background:#102019; border-left:5px solid #67e495; border-bottom:3px solid #67e495; }
QFrame#OperationFrame[operationKind="error"] { background:#271415; border-left:5px solid #ff6b6b; border-bottom:3px solid #ff6b6b; }
QPushButton#CurrentStatusButton[currentStatusKind="not_selected"] { background:#30363f; border-color:#68727e; color:#d4d9df; }
QSlider#SeekSlider::groove:horizontal { height:12px; background:#2a333e; border-radius:6px; }
QSlider#SeekSlider::handle:horizontal { width:24px; margin:-7px 0; border-radius:12px; background:#43d17d; }
QSlider#VolumeSlider::groove:horizontal { height:6px; background:#2a333e; border-radius:3px; }
"""

LIGHT_OVERRIDE = r"""
QFrame#OperationFrame { background:#f4f8fb; border:1px solid #c9d6df; border-left:5px solid #8797a5; border-bottom:3px solid #4e9aaa; border-radius:8px; }
QFrame#OperationFrame[operationKind="scan"] { background:#eef6ff; border-color:#a9c9e8; border-left:6px solid #5ca3ff; border-bottom:3px solid #5ca3ff; }
QFrame#OperationFrame[operationKind="online"] { background:#f5f0ff; border-color:#c8b6eb; border-left:6px solid #8a63d2; border-bottom:3px solid #8a63d2; }
QFrame#OperationFrame[operationKind="review"] { background:#fff8e8; border-color:#ddc28c; border-left:6px solid #d7962f; border-bottom:3px solid #d7962f; }
QFrame#OperationFrame[operationKind="export"] { background:#eefafa; border-color:#a9d4d8; border-left:6px solid #3f96a1; border-bottom:3px solid #3f96a1; }
QFrame#OperationFrame[operationKind="done"] { background:#edf9f2; border-left:5px solid #35a966; border-bottom:3px solid #35a966; }
QFrame#OperationFrame[operationKind="error"] { background:#fff0f1; border-left:5px solid #d7525c; border-bottom:3px solid #d7525c; }
QPushButton#CurrentStatusButton[currentStatusKind="not_selected"] { background:#e2e6ea; border-color:#a3adb7; color:#4e5964; }
QSlider#SeekSlider::groove:horizontal { height:12px; background:#cad3dc; border-radius:6px; }
QSlider#SeekSlider::handle:horizontal { width:24px; margin:-7px 0; border-radius:12px; background:#2cad68; }
QSlider#VolumeSlider::groove:horizontal { height:6px; background:#cad3dc; border-radius:3px; }
"""


def install_v0411_base_overrides() -> None:
    """Keep v0.4.11 overrides when MainWindow reapplies the base theme."""
    from audio_library_organizer.ui import theme as base_theme

    if DARK_OVERRIDE not in base_theme.DARK_STYLE:
        base_theme.DARK_STYLE = base_theme.DARK_STYLE + DARK_OVERRIDE
    if hasattr(base_theme, 'APP_STYLE') and DARK_OVERRIDE not in base_theme.APP_STYLE:
        base_theme.APP_STYLE = base_theme.APP_STYLE + DARK_OVERRIDE


install_v0411_base_overrides()

def style_for_v0411(theme: str, *, system_is_dark: bool | None = None) -> str:
    theme = theme if theme in {'dark', 'light', 'system'} else 'dark'
    if theme == 'light':
        return LIGHT_OVERRIDE
    if theme == 'system':
        if system_is_dark is None:
            try:
                from PySide6.QtGui import QGuiApplication
                system_is_dark = QGuiApplication.palette().window().color().lightness() < 128
            except Exception:
                system_is_dark = True
        return DARK_OVERRIDE if system_is_dark else LIGHT_OVERRIDE
    return DARK_OVERRIDE
