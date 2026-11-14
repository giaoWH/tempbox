"""Painted widgets for the TempBox floating panel."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from .formatting import format_size
from .storage import FileRecord
from .ui_theme import Theme


def _pen(color: QColor, width: float = 1.5) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


_KIND_ACCENTS = {
    "pdf": "#D6534C",
    "image": "#3B82F6",
    "archive": "#C9820A",
    "text": "#8E8E93",
    "doc": "#5B7BE0",
}

_SUFFIX_KINDS = {
    "pdf": "pdf",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "heic": "image",
    "webp": "image",
    "tiff": "image",
    "bmp": "image",
    "svg": "image",
    "zip": "archive",
    "rar": "archive",
    "7z": "archive",
    "tar": "archive",
    "gz": "archive",
    "dmg": "archive",
    "txt": "text",
    "md": "text",
    "markdown": "text",
    "rtf": "text",
    "log": "text",
    "doc": "doc",
    "docx": "doc",
    "pages": "doc",
}


def file_kind(name: str) -> str:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _SUFFIX_KINDS.get(suffix, "text")


def _draw_file_tile(painter: QPainter, rect: QRectF, kind: str, theme: Theme) -> None:
    accent = QColor(_KIND_ACCENTS.get(kind, theme.secondary))
    tint = QColor(accent)
    tint.setAlpha(30 if not theme.is_dark else 42)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tint)
    painter.drawRoundedRect(rect, 8, 8)

    border = QColor(accent)
    border.setAlpha(70)
    painter.setPen(_pen(border, 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, 8, 8)

    page = rect.adjusted(
        rect.width() * 0.29,
        rect.height() * 0.22,
        -rect.width() * 0.29,
        -rect.height() * 0.22,
    )
    painter.setPen(_pen(accent, 1.35))
    path = QPainterPath()
    fold = page.width() * 0.28
    path.moveTo(page.left(), page.top())
    path.lineTo(page.right() - fold, page.top())
    path.lineTo(page.right(), page.top() + fold)
    path.lineTo(page.right(), page.bottom())
    path.lineTo(page.left(), page.bottom())
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(
        QPointF(page.right() - fold, page.top()), QPointF(page.right() - fold, page.top() + fold)
    )
    painter.drawLine(
        QPointF(page.right() - fold, page.top() + fold), QPointF(page.right(), page.top() + fold)
    )
    painter.drawLine(
        QPointF(page.left() + page.width() * 0.22, page.center().y()),
        QPointF(page.right() - page.width() * 0.22, page.center().y()),
    )


class FileRow(QWidget):
    """One file in the compact panel list."""

    menu_requested = Signal(object)
    checked_changed = Signal(object, bool)
    opened = Signal(object)

    ROW_HEIGHT = 56

    def __init__(
        self,
        record: FileRecord,
        remaining_text: str,
        tone: str,
        tooltip: str,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.remaining_text = remaining_text
        self.tone = tone
        self._theme = theme
        self._hovered = False
        self._selection_mode = False
        self._checked = False
        self._menu_rect = None
        self._checkbox_rect = None
        self.setFixedHeight(self.ROW_HEIGHT)
        self.setMouseTracking(True)
        self.setToolTip(tooltip)

    # -- state ---------------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_selection_mode(self, enabled: bool) -> None:
        self._selection_mode = enabled
        self.update()

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self.update()

    # -- painting ------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self._theme
        row_rect = QRectF(self.rect()).adjusted(2, 1, -2, -1)

        if self._hovered or self._checked:
            background = QColor(theme.selected if self._checked else theme.hover)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(row_rect, 10, 10)

        height = float(self.height())
        center_y = height / 2.0
        left = 10.0

        if self._selection_mode:
            checkbox = QRectF(left, center_y - 8, 16, 16)
            self._checkbox_rect = checkbox
            self._draw_checkbox(painter, checkbox)
            left += 26

        tile = QRectF(left, center_y - 16, 32, 32)
        _draw_file_tile(painter, tile, file_kind(self.record.original_name), theme)
        left += 42

        right = float(self.width()) - 10
        menu_rect = QRectF(right - 20, center_y - 11, 20, 22)
        self._menu_rect = menu_rect
        right -= 28

        remaining_font = QFont()
        remaining_font.setPixelSize(11)
        remaining_font.setWeight(QFont.Weight.Medium)
        remaining_metrics = QFontMetrics(remaining_font)
        remaining_width = remaining_metrics.horizontalAdvance(self.remaining_text)
        color = QColor(
            {
                "soon": theme.amber,
                "expired": theme.red,
                "failed": theme.red,
                "none": theme.tertiary,
            }.get(self.tone, theme.secondary)
        )
        show_dot = self.tone in ("soon", "expired", "failed")
        dot_space = 9.0 if show_dot else 0.0
        text_left = right - remaining_width - dot_space

        painter.setFont(remaining_font)
        painter.setPen(color)
        painter.drawText(
            QRectF(text_left + dot_space, 0, right - text_left - dot_space, height),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.remaining_text,
        )
        if show_dot:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(text_left + 1.5, center_y), 2.2, 2.2)

        name_font = QFont()
        name_font.setPixelSize(13)
        name_font.setWeight(QFont.Weight.Medium)
        name_metrics = QFontMetrics(name_font)
        name_width = max(24.0, text_left - 14 - left)
        elided_name = name_metrics.elidedText(
            self.record.original_name, Qt.TextElideMode.ElideRight, int(name_width)
        )
        painter.setFont(name_font)
        painter.setPen(QColor(theme.text))
        painter.drawText(
            QRectF(left, center_y - 19, name_width, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_name,
        )

        size_font = QFont()
        size_font.setPixelSize(11)
        painter.setFont(size_font)
        painter.setPen(QColor(theme.secondary))
        painter.drawText(
            QRectF(left, center_y + 1, name_width, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            format_size(self.record.size),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.tertiary if not self._hovered else theme.secondary))
        for offset in (-4.0, 0.0, 4.0):
            painter.drawEllipse(QPointF(menu_rect.center().x() + offset, center_y), 1.25, 1.25)
        painter.end()

    def _draw_checkbox(self, painter: QPainter, rect: QRectF) -> None:
        theme = self._theme
        if self._checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.accent))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(_pen(QColor("#FFFFFF"), 1.7))
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(rect.left() + 4.2, rect.center().y()),
                        QPointF(rect.center().x() - 0.6, rect.bottom() - 4.6),
                        QPointF(rect.right() - 3.8, rect.top() + 4.4),
                    ]
                )
            )
        else:
            painter.setPen(_pen(QColor(theme.tertiary), 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)

    # -- interaction ---------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        if self._menu_rect is not None and self._menu_rect.contains(position):
            self.menu_requested.emit(self)
            return
        if self._selection_mode:
            self.checked_changed.emit(self, not self._checked)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._selection_mode:
            self.opened.emit(self)


class EmptyState(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title_text = "No files yet"
        self.subtitle_text = "Drop files here and we'll take care of the rest."
        self.setMinimumHeight(148)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_state(self, title: str, subtitle: str) -> None:
        self.title_text = title
        self.subtitle_text = subtitle
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self._theme
        center_x = self.width() / 2
        center_y = self.height() / 2

        tray = QRectF(center_x - 21, center_y - 42, 42, 34)
        painter.setPen(_pen(QColor(theme.tertiary), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(tray.left(), tray.top() + 8, 42, 26), 6, 6)
        painter.drawLine(QPointF(center_x, tray.top()), QPointF(center_x, tray.top() + 22))
        painter.drawLine(
            QPointF(center_x - 6, tray.top() + 15), QPointF(center_x, tray.top() + 22)
        )
        painter.drawLine(
            QPointF(center_x + 6, tray.top() + 15), QPointF(center_x, tray.top() + 22)
        )

        title_font = QFont()
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(QColor(theme.text))
        painter.drawText(
            QRectF(0, center_y + 4, self.width(), 20),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.title_text,
        )

        subtitle_font = QFont()
        subtitle_font.setPixelSize(11)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(theme.secondary))
        painter.drawText(
            QRectF(20, center_y + 28, self.width() - 40, 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.subtitle_text,
        )
        painter.end()


class DropZone(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._active = False
        self._hint = "Keep for 1 day by default"
        self.setFixedHeight(60)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_hint(self, text: str) -> None:
        self._hint = text
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def is_active(self) -> bool:
        return self._active

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self._theme
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)

        if self._active:
            background = QColor(theme.accent_soft)
            pen = _pen(QColor(theme.accent), 1.4)
        else:
            background = QColor(theme.drop_bg)
            pen = _pen(QColor(theme.panel_border), 1.0)
        painter.setPen(pen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 10, 10)

        icon_center = QPointF(26, self.height() / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        icon_background = QColor(theme.accent)
        icon_background.setAlpha(40 if self._active else 26)
        painter.setBrush(icon_background)
        painter.drawEllipse(icon_center, 13, 13)
        painter.setPen(_pen(QColor(theme.accent), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(
            QPointF(icon_center.x(), icon_center.y() - 6),
            QPointF(icon_center.x(), icon_center.y() + 3),
        )
        painter.drawLine(
            QPointF(icon_center.x() - 3.6, icon_center.y() - 0.2),
            QPointF(icon_center.x(), icon_center.y() + 3.6),
        )
        painter.drawLine(
            QPointF(icon_center.x() + 3.6, icon_center.y() - 0.2),
            QPointF(icon_center.x(), icon_center.y() + 3.6),
        )

        title_font = QFont()
        title_font.setPixelSize(12)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(QColor(theme.text))
        painter.drawText(
            QRectF(48, self.height() / 2 - 17, self.width() - 62, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Drop files here",
        )
        hint_font = QFont()
        hint_font.setPixelSize(11)
        painter.setFont(hint_font)
        painter.setPen(QColor(theme.secondary))
        painter.drawText(
            QRectF(48, self.height() / 2 + 2, self.width() - 62, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            self._hint,
        )
        painter.end()


class PanelSurface(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setFixedWidth(420)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(_pen(QColor(self._theme.panel_border), 1.0))
        painter.setBrush(QColor(self._theme.panel))
        painter.drawRoundedRect(rect, 14, 14)
        painter.end()
