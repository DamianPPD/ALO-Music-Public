"""Small paint adapters; standard Qt actions, models and keyboard handling."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QBrush
from PySide6.QtWidgets import (
    QComboBox, QMenu, QStyle, QStyleOptionComboBox, QStyleOptionMenuItem,
    QStyleOptionViewItem, QStyledItemDelegate, QStylePainter,
)

from audio_library_organizer.ui.i18n import ui_text


class AccentMenu(QMenu):
    """Paint accent text without QWidgetAction ownership or altered input."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setClipRegion(event.region())
        panel = QStyleOptionMenuItem()
        panel.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelMenu, panel, painter, self)
        for action in self.actions():
            option = QStyleOptionMenuItem()
            self.initStyleOption(option, action)
            option.rect = self.actionGeometry(action)
            accent = action.property('accent')
            text = option.text
            if accent:
                option.text = ''
            self.style().drawControl(QStyle.ControlElement.CE_MenuItem, option, painter, self)
            if not accent:
                continue
            # Keep the native icon/check column and QSS hover/background.
            rect = option.rect.adjusted(option.maxIconWidth + 16, 0, -16, 0)
            painter.setFont(option.font)
            label, separator, description = text.partition(' — ')
            painter.setPen(QColor(accent))
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            if separator:
                rect.setLeft(rect.left() + QFontMetrics(option.font).horizontalAdvance(label))
                painter.setPen(option.palette.color(QPalette.ColorRole.WindowText))
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 separator + description)


class _FilterDelegate(QStyledItemDelegate):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def paint(self, painter, option, index):
        clean = QStyleOptionViewItem(option)
        self.initStyleOption(clean, index)
        selected = index.row() == self.combo.currentIndex()
        clean.font.setBold(selected)
        clean.font.setItalic(False)
        text, clean.text = clean.text, ''
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        if selected:
            clean.backgroundBrush = QBrush(QColor('#203b45'))
        # Native highlighting remains available for keyboard/hover navigation.
        self.combo.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, clean, painter, self.combo.view())
        rect = self.combo.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, clean, self.combo.view())
        rect.adjust(2, 0, -22, 0)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        painter.save()
        painter.setFont(clean.font)
        painter.setPen(brush.color() if brush is not None else clean.palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if selected:
            painter.drawText(option.rect.adjusted(0, 0, -6, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, '✓')
        painter.restore()


class LibraryFilterCombo(QComboBox):
    def __init__(self, prefix, parent=None):
        super().__init__(parent)
        self.prefix = prefix
        self.setItemDelegate(_FilterDelegate(self))

    def fit_labels(self, minimum):
        """Fit both languages/current font without clipping the longest state."""
        self._minimum_label_width = minimum
        regular = self.fontMetrics()
        bold = QFont(self.font())
        bold.setBold(True)
        values = QFontMetrics(bold)
        width = max((values.horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        self.setFixedWidth(max(minimum, regular.horizontalAdvance(ui_text(self, self.prefix) + ': ') + width + 42))
        self.view().setMinimumWidth(self.width())
        self.update()

    def setItemText(self, index, text):
        super().setItemText(index, text)
        if hasattr(self, '_minimum_label_width'):
            self.fit_labels(self._minimum_label_width)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, '_minimum_label_width'):
            self.fit_labels(self._minimum_label_width)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ''
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        rect = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                          QStyle.SubControl.SC_ComboBoxEditField, self)
        painter.setClipRect(rect)
        prefix = ui_text(self, self.prefix) + ': '
        painter.setFont(self.font())
        painter.setPen(QColor('#84939e'))
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, prefix)
        rect.setLeft(rect.left() + self.fontMetrics().horizontalAdvance(prefix))
        font = QFont(self.font())
        font.setBold(True)
        font.setItalic(False)
        painter.setFont(font)
        brush = self.currentData(Qt.ItemDataRole.ForegroundRole)
        painter.setPen(brush.color() if brush is not None else QColor('#d9e5e8'))
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.currentText())
