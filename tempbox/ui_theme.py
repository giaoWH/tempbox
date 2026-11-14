"""Visual theme, styles and small painted icons for the TempBox panel."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


@dataclass(frozen=True)
class Theme:
    is_dark: bool
    panel: str
    panel_border: str
    text: str
    secondary: str
    tertiary: str
    hover: str
    selected: str
    divider: str
    input_bg: str
    input_border: str
    accent: str
    accent_soft: str
    amber: str
    red: str
    menu_bg: str
    menu_border: str
    menu_selected: str
    button_hover: str
    drop_bg: str


LIGHT = Theme(
    is_dark=False,
    panel="#F7F7F9",
    panel_border="#E2E2E7",
    text="#1D1D1F",
    secondary="#86868B",
    tertiary="#A7A7AC",
    hover="#ECECF0",
    selected="#E4F0FF",
    divider="#E8E8EC",
    input_bg="#FFFFFF",
    input_border="#DCDCE2",
    accent="#0A84FF",
    accent_soft="#E6F1FF",
    amber="#B77500",
    red="#C9413D",
    menu_bg="#FFFFFF",
    menu_border="#E2E2E7",
    menu_selected="#E6F1FF",
    button_hover="#ECECF0",
    drop_bg="#FFFFFF",
)

DARK = Theme(
    is_dark=True,
    panel="#26262A",
    panel_border="#3A3A41",
    text="#F2F2F5",
    secondary="#9C9CA3",
    tertiary="#75757C",
    hover="#323238",
    selected="#22374F",
    divider="#34343A",
    input_bg="#1E1E22",
    input_border="#3A3A41",
    accent="#0A84FF",
    accent_soft="#1B3350",
    amber="#E0A64B",
    red="#FF6961",
    menu_bg="#2C2C31",
    menu_border="#404047",
    menu_selected="#26405E",
    button_hover="#323238",
    drop_bg="#2B2B30",
)


def build_styles(theme: Theme) -> str:
    return f"""
    QWidget {{ color: {theme.text}; font-size: 13px; }}
    QLabel {{ background: transparent; }}
    QLabel#PanelTitle {{ font-size: 13px; font-weight: 600; }}
    QLabel#StatsLabel {{ color: {theme.secondary}; font-size: 11px; }}
    QToolButton#HeaderButton {{
        background: transparent; border: none; border-radius: 6px;
        padding: 3px 7px; color: {theme.secondary}; font-size: 11px;
    }}
    QToolButton#HeaderButton:hover {{ background: {theme.button_hover}; color: {theme.text}; }}
    QToolButton#IconButton {{
        background: transparent; border: none; border-radius: 6px; padding: 4px;
    }}
    QToolButton#IconButton:hover {{ background: {theme.button_hover}; }}
    QLineEdit#SearchField {{
        background: {theme.input_bg}; border: 1px solid {theme.input_border};
        border-radius: 8px; padding: 4px 8px; color: {theme.text}; font-size: 12px;
        selection-background-color: {theme.accent};
    }}
    QLineEdit#SearchField:focus {{ border: 1px solid {theme.accent}; }}
    QToolButton#SortButton {{
        background: transparent; border: none; border-radius: 8px;
        padding: 4px 20px 4px 8px; color: {theme.secondary}; font-size: 11px;
    }}
    QToolButton#SortButton:hover {{ background: {theme.button_hover}; color: {theme.text}; }}
    QToolButton#SortButton::menu-indicator {{
        subcontrol-origin: padding;
        subcontrol-position: right center;
        right: 5px;
    }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px 0; }}
    QScrollBar::handle:vertical {{
        background: {theme.tertiary}; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QPushButton#BatchButton {{
        background: transparent; border: none; border-radius: 6px;
        padding: 4px 8px; color: {theme.secondary}; font-size: 11px;
    }}
    QPushButton#BatchButton:hover {{ background: {theme.button_hover}; color: {theme.text}; }}
    QPushButton#BatchButton:disabled {{ color: {theme.tertiary}; }}
    QPushButton#FooterButton {{
        background: transparent; border: none; border-radius: 6px;
        padding: 3px 7px; color: {theme.secondary}; font-size: 11px;
    }}
    QPushButton#FooterButton:hover {{ background: {theme.button_hover}; color: {theme.text}; }}
    QLabel#FooterText {{ color: {theme.secondary}; font-size: 11px; }}
    QLabel#FooterHint {{ color: {theme.tertiary}; font-size: 11px; }}
    QLabel#PausedLabel {{ color: {theme.amber}; font-size: 11px; font-weight: 600; }}
    QLabel#BatchCount {{ color: {theme.text}; font-size: 11px; font-weight: 600; }}
    """


def menu_styles(theme: Theme) -> str:
    return f"""
    QMenu {{
        background: {theme.menu_bg}; border: 1px solid {theme.menu_border};
        border-radius: 10px; padding: 5px; font-size: 12px; color: {theme.text};
    }}
    QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 6px; background: transparent; }}
    QMenu::item:selected {{ background: {theme.menu_selected}; }}
    QMenu::separator {{ height: 1px; background: {theme.divider}; margin: 4px 8px; }}
    """


def _pixmap(size: float, dpr: int = 2) -> QPixmap:
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _icon(draw: Callable[[QPainter], None], size: float = 16, dpr: int = 2) -> QIcon:
    pixmap = _pixmap(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(dpr, dpr)
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def _pen(color: QColor, width: float = 1.5) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def search_icon(theme: Theme) -> QIcon:
    color = QColor(theme.tertiary)

    def draw(painter: QPainter) -> None:
        painter.setPen(_pen(color, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(3.6, 3.6, 7.2, 7.2))
        painter.drawLine(QPointF(10.8, 10.8), QPointF(13.4, 13.4))

    return _icon(draw)


def settings_icon(theme: Theme) -> QIcon:
    color = QColor(theme.tertiary)

    def draw(painter: QPainter) -> None:
        center = QPointF(8.0, 8.0)
        painter.setPen(_pen(color, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, 2.1, 2.1)
        for index in range(8):
            angle = index * math.pi / 4.0
            direction = QPointF(math.cos(angle), math.sin(angle))
            painter.drawLine(
                QPointF(
                    center.x() + direction.x() * 3.5,
                    center.y() + direction.y() * 3.5,
                ),
                QPointF(
                    center.x() + direction.x() * 5.4,
                    center.y() + direction.y() * 5.4,
                ),
            )

    return _icon(draw)


def brand_pixmap(size: int = 26) -> QPixmap:
    pixmap = _pixmap(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0A84FF"))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size * 0.28, size * 0.28)
    painter.setPen(_pen(QColor("#FFFFFF"), max(1.3, size * 0.065)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    inset = size * 0.26
    painter.drawRoundedRect(
        QRectF(inset, inset, size - inset * 2, size - inset * 2), size * 0.12, size * 0.12
    )
    center = size / 2
    painter.drawLine(QPointF(center, size * 0.34), QPointF(center, size * 0.60))
    painter.drawLine(QPointF(center - size * 0.09, size * 0.52), QPointF(center, size * 0.62))
    painter.drawLine(QPointF(center + size * 0.09, size * 0.52), QPointF(center, size * 0.62))
    painter.end()
    return pixmap
