"""桌面端的视觉常量与双主题（白天 / 夜间）。

主题只描述外观，不承载任何业务规则；控件结构由 main_window.py 负责。
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette

LIGHT = {
    "canvas": "#eef2f7",
    "surface": "#ffffff",
    "surface_alt": "#fbfcfe",
    "border": "#e4e9f0",
    "border_strong": "#d6dde8",
    "text": "#0f172a",
    "text_muted": "#64748b",
    "text_faint": "#94a3b8",
    "accent": "#2f5fe0",
    "accent_hover": "#274fbd",
    "accent_pressed": "#1f47a3",
    "accent_soft": "#eef2ff",
    "accent_muted": "#b9c6e8",
    "success": "#0f9d76",
    "success_soft": "#e9f8f1",
    "warning": "#c2820a",
    "warning_soft": "#fdf6e6",
    "danger": "#d64545",
    "danger_soft": "#fdefef",
    "neutral_soft": "#f1f4f8",
    "chip_bg": "#e6ebf3",
    "chip_fg": "#64748b",
    "input_bg": "#ffffff",
    "button_bg": "#ffffff",
    "button_fg": "#334155",
    "button_hover": "#f5f8fd",
    "button_pressed": "#eef2f8",
    "disabled_bg": "#f1f4f8",
    "disabled_fg": "#c3cbd8",
    "ghost_hover": "#eef2f7",
    "table_header": "#f7f9fc",
    "table_alt": "#fafbfd",
    "table_line": "#f1f4f8",
    "table_selected": "#eef2ff",
    "scroll": "#cbd5e1",
    "scroll_hover": "#aab6c6",
    "tooltip_bg": "#0f172a",
    "tooltip_fg": "#ffffff",
    "on_accent": "#ffffff",
}

DARK = {
    "canvas": "#0e1626",
    "surface": "#18212f",
    "surface_alt": "#151d29",
    "border": "#2a3850",
    "border_strong": "#3a4a63",
    "text": "#e6edf7",
    "text_muted": "#9fb0c7",
    "text_faint": "#7b8ca3",
    "accent": "#4d84f0",
    "accent_hover": "#6b99f5",
    "accent_pressed": "#3a6ed4",
    "accent_soft": "#1b2b48",
    "accent_muted": "#31456f",
    "success": "#35c08e",
    "success_soft": "#13312a",
    "warning": "#e0a33a",
    "warning_soft": "#332811",
    "danger": "#f07a7a",
    "danger_soft": "#3a1f22",
    "neutral_soft": "#1c2637",
    "chip_bg": "#233149",
    "chip_fg": "#b3c4da",
    "input_bg": "#131b27",
    "button_bg": "#1f2a3d",
    "button_fg": "#d6e0ee",
    "button_hover": "#26334a",
    "button_pressed": "#1a2434",
    "disabled_bg": "#18212f",
    "disabled_fg": "#5b6b83",
    "ghost_hover": "#233149",
    "table_header": "#1e293b",
    "table_alt": "#1a2331",
    "table_line": "#26324a",
    "table_selected": "#24406e",
    "scroll": "#3a4a63",
    "scroll_hover": "#4e617d",
    "tooltip_bg": "#e2e8f0",
    "tooltip_fg": "#0f172a",
    "on_accent": "#ffffff",
}

THEMES = {"light": LIGHT, "dark": DARK}
THEME_LABELS = {"light": "白天", "dark": "夜间"}


def build_stylesheet(theme: str = "light") -> str:
    """按主题生成整套样式表。"""
    c = THEMES.get(theme, LIGHT)
    return f"""
QWidget {{
    color: {c['text']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget#pageContent, QScrollArea#pageScroll, QDialog {{
    background: {c['canvas']};
}}
QScrollArea#pageScroll {{
    border: none;
}}
QScrollArea#pageScroll > QWidget > QWidget {{
    background: {c['canvas']};
}}

/* ---------- 页头 ---------- */
QLabel#pageTitle {{
    font-size: 21px;
    font-weight: 700;
    color: {c['text']};
}}
QLabel#pageSubtitle {{
    font-size: 13px;
    color: {c['text_muted']};
}}
QLabel#versionChip, QLabel#softChip {{
    border-radius: 11px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#versionChip {{
    background: {c['accent_soft']};
    color: {c['accent']};
}}
QLabel#softChip {{
    background: {c['chip_bg']};
    color: {c['chip_fg']};
}}

/* ---------- 主题切换 ---------- */
QFrame#themeSwitch {{
    background: {c['chip_bg']};
    border-radius: 15px;
}}
QPushButton#themeSegment {{
    background: transparent;
    border: none;
    border-radius: 13px;
    padding: 4px 14px;
    color: {c['text_muted']};
    font-weight: 600;
}}
QPushButton#themeSegment:hover {{
    background: {c['ghost_hover']};
    color: {c['text']};
}}
QPushButton#themeSegment:checked {{
    background: {c['accent']};
    color: {c['on_accent']};
}}

/* ---------- 卡片 ---------- */
QFrame#sectionCard {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {c['text']};
}}
QLabel#sectionHint {{
    font-size: 12px;
    color: {c['text_faint']};
}}
QLabel#stepBadge {{
    background: {c['accent']};
    color: {c['on_accent']};
    border-radius: 13px;
    font-size: 12px;
    font-weight: 700;
}}
QLabel#fieldLabel {{
    color: {c['text']};
    font-weight: 600;
}}
QLabel#fieldHint {{
    color: {c['text_faint']};
    font-size: 12px;
}}
QLabel#mutedValue {{
    color: {c['text_muted']};
}}
QLabel#monoValue {{
    color: {c['text']};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}}
QLabel#checkValue {{
    color: {c['success']};
    font-weight: 600;
}}
QLabel#checkPlain {{
    color: {c['text']};
}}
QLabel#outputError {{
    color: {c['danger']};
    font-size: 12px;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QComboBox {{
    background: {c['input_bg']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {c['accent']};
    selection-color: {c['on_accent']};
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: {c['text_faint']};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QLineEdit:disabled, QComboBox:disabled {{
    background: {c['disabled_bg']};
    color: {c['disabled_fg']};
}}
QLineEdit::placeholder {{
    color: {c['text_faint']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c['text_muted']};
    width: 0;
    height: 0;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']};
    outline: none;
    padding: 4px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {c['button_bg']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 7px 16px;
    color: {c['button_fg']};
    font-weight: 600;
}}
QPushButton:hover {{
    background: {c['button_hover']};
    border-color: {c['text_faint']};
}}
QPushButton:pressed {{
    background: {c['button_pressed']};
}}
QPushButton:disabled {{
    background: {c['disabled_bg']};
    border-color: {c['border']};
    color: {c['disabled_fg']};
}}
QPushButton#primaryButton {{
    background: {c['accent']};
    border: 1px solid {c['accent']};
    color: {c['on_accent']};
}}
QPushButton#primaryButton:hover {{
    background: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}
QPushButton#primaryButton:pressed {{
    background: {c['accent_pressed']};
    border-color: {c['accent_pressed']};
}}
QPushButton#primaryButton:disabled {{
    background: {c['accent_muted']};
    border-color: {c['accent_muted']};
    color: {c['on_accent']};
}}
QPushButton#ghostButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {c['text_muted']};
    padding: 7px 10px;
}}
QPushButton#ghostButton:hover {{
    background: {c['ghost_hover']};
    color: {c['text']};
}}
QPushButton#ghostButton:disabled {{
    background: transparent;
    color: {c['disabled_fg']};
}}
QPushButton#dangerButton {{
    background: {c['surface']};
    border: 1px solid {c['danger']};
    color: {c['danger']};
}}
QPushButton#dangerButton:hover {{
    background: {c['danger_soft']};
}}
QPushButton#dangerButton:disabled {{
    background: {c['disabled_bg']};
    border-color: {c['border']};
    color: {c['disabled_fg']};
}}
QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {c['accent']};
    font-weight: 600;
    padding: 4px 2px;
    text-align: left;
}}
QPushButton#linkButton:hover {{
    color: {c['accent_hover']};
    text-decoration: underline;
}}

/* ---------- 状态条 ---------- */
QFrame#statusBanner {{
    background: {c['accent_soft']};
    border-radius: 10px;
}}
QFrame#statusBanner[state="neutral"] {{
    background: {c['neutral_soft']};
}}
QFrame#statusBanner[state="info"] {{
    background: {c['accent_soft']};
}}
QFrame#statusBanner[state="success"] {{
    background: {c['success_soft']};
}}
QFrame#statusBanner[state="warning"] {{
    background: {c['warning_soft']};
}}
QFrame#statusBanner[state="error"] {{
    background: {c['danger_soft']};
}}
QFrame#statusRail {{
    background: {c['accent']};
    border-radius: 2px;
}}
QFrame#statusRail[state="neutral"] {{ background: {c['text_faint']}; }}
QFrame#statusRail[state="info"] {{ background: {c['accent']}; }}
QFrame#statusRail[state="success"] {{ background: {c['success']}; }}
QFrame#statusRail[state="warning"] {{ background: {c['warning']}; }}
QFrame#statusRail[state="error"] {{ background: {c['danger']}; }}
QLabel#statusText {{
    font-size: 13px;
    color: {c['text']};
}}
QLabel#statusTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {c['text']};
}}

QProgressBar {{
    background: {c['border']};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: 4px;
}}

/* ---------- 摘要卡片 ---------- */
QFrame#featureCard {{
    background: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#featureCard[tone="add"] {{ border-left: 3px solid {c['success']}; }}
QFrame#featureCard[tone="delete"] {{ border-left: 3px solid {c['danger']}; }}
QFrame#featureCard[tone="info"] {{ border-left: 3px solid {c['accent']}; }}
QLabel#featureTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {c['text']};
}}
QLabel#featureStatus {{
    font-size: 12px;
    color: {c['text_muted']};
}}
QLabel#featureMetric {{
    color: {c['text_muted']};
    font-size: 12px;
}}

/* ---------- 问题表 ---------- */
QTableView {{
    background: {c['surface']};
    alternate-background-color: {c['table_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: {c['table_selected']};
    selection-color: {c['text']};
    outline: none;
}}
QTableView::item {{
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid {c['table_line']};
}}
QTableView::item:selected {{
    background: {c['table_selected']};
    color: {c['text']};
}}
QHeaderView::section {{
    background: {c['table_header']};
    color: {c['text_muted']};
    padding: 9px 8px;
    border: none;
    border-bottom: 1px solid {c['border']};
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {c['table_header']};
    border: none;
}}
QLabel#emptyHint {{
    color: {c['text_faint']};
    font-size: 13px;
}}

/* ---------- 高级信息 ---------- */
QFrame#advancedPanel {{
    background: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['scroll']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['scroll_hover']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c['scroll']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['scroll_hover']};
}}

/* ---------- 对话框与提示 ---------- */
QMessageBox, QDialog {{
    background: {c['surface']};
}}
QMessageBox QLabel {{
    color: {c['text']};
}}
QToolTip {{
    background: {c['tooltip_bg']};
    color: {c['tooltip_fg']};
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}}
"""


def detect_system_theme() -> str:
    """读取 Windows 的应用主题；不可用时回退到白天主题。"""
    if sys.platform != "win32":
        return "light"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return "light"
    return "light" if value else "dark"


def apply_theme(app, theme: str) -> None:
    """应用主题样式与调色板，使原生绘制的控件也跟随主题。"""
    c = THEMES.get(theme, LIGHT)
    app.setStyleSheet(build_stylesheet(theme))
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["surface"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["input_bg"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["table_alt"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["button_bg"]))
    palette.setColor(QPalette.ButtonText, QColor(c["button_fg"]))
    palette.setColor(QPalette.BrightText, QColor(c["danger"]))
    palette.setColor(QPalette.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(c["on_accent"]))
    palette.setColor(QPalette.ToolTipBase, QColor(c["tooltip_bg"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["tooltip_fg"]))
    palette.setColor(QPalette.PlaceholderText, QColor(c["text_faint"]))
    palette.setColor(QPalette.Light, QColor(c["surface_alt"]))
    palette.setColor(QPalette.Mid, QColor(c["border"]))
    palette.setColor(QPalette.Dark, QColor(c["canvas"]))
    app.setPalette(palette)


# 兼容旧引用：默认主题的样式表。
APP_STYLE = build_stylesheet("light")
