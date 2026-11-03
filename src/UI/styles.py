"""桌面端的视觉常量与浅色主题。

主题只描述外观，不承载任何业务规则；控件结构由 main_window.py 负责。
"""

from __future__ import annotations

# 配色：中性冷灰底 + 白色卡片 + 单一强调色，状态色只用于语义表达。
CANVAS = "#eef2f7"
SURFACE = "#ffffff"
BORDER = "#e4e9f0"
BORDER_STRONG = "#d6dde8"
TEXT = "#0f172a"
TEXT_MUTED = "#64748b"
TEXT_FAINT = "#94a3b8"
ACCENT = "#2f5fe0"
ACCENT_HOVER = "#274fbd"
ACCENT_PRESSED = "#1f47a3"
ACCENT_SOFT = "#eef2ff"
ACCENT_MUTED = "#b9c6e8"
SUCCESS = "#0f9d76"
SUCCESS_SOFT = "#e9f8f1"
WARNING = "#c2820a"
WARNING_SOFT = "#fdf6e6"
DANGER = "#d64545"
DANGER_SOFT = "#fdefef"

APP_STYLE = f"""
QWidget {{
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget#pageContent, QScrollArea#pageScroll {{
    background: {CANVAS};
}}
QScrollArea#pageScroll {{
    border: none;
}}
QScrollArea#pageScroll > QWidget > QWidget {{
    background: {CANVAS};
}}

/* ---------- 页头 ---------- */
QLabel#pageTitle {{
    font-size: 21px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#pageSubtitle {{
    font-size: 13px;
    color: {TEXT_MUTED};
}}
QLabel#versionChip, QLabel#softChip {{
    border-radius: 11px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#versionChip {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
}}
QLabel#softChip {{
    background: #e6ebf3;
    color: {TEXT_MUTED};
}}

/* ---------- 卡片 ---------- */
QFrame#sectionCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#sectionHint {{
    font-size: 12px;
    color: {TEXT_FAINT};
}}
QLabel#stepBadge {{
    background: {ACCENT};
    color: #ffffff;
    border-radius: 13px;
    font-size: 12px;
    font-weight: 700;
}}
QLabel#fieldLabel {{
    color: {TEXT};
    font-weight: 600;
}}
QLabel#fieldHint {{
    color: {TEXT_FAINT};
    font-size: 12px;
}}
QLabel#mutedValue {{
    color: {TEXT_MUTED};
}}
QLabel#monoValue {{
    color: {TEXT};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}}
QLabel#checkValue {{
    color: {SUCCESS};
    font-weight: 600;
}}
QLabel#checkPlain {{
    color: {TEXT};
}}
QLabel#outputError {{
    color: {DANGER};
    font-size: 12px;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: #b9c4d4;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled {{
    background: #f4f6f9;
    color: {TEXT_FAINT};
}}
QLineEdit::placeholder {{
    color: {TEXT_FAINT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_MUTED};
    width: 0;
    height: 0;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
    padding: 4px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 7px 16px;
    color: #334155;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #f5f8fd;
    border-color: #b9c4d4;
}}
QPushButton:pressed {{
    background: #eef2f8;
}}
QPushButton:disabled {{
    background: #f1f4f8;
    border-color: #e4e9f0;
    color: {TEXT_FAINT};
}}
QPushButton#primaryButton {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
}}
QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:pressed {{
    background: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}
QPushButton#primaryButton:disabled {{
    background: {ACCENT_MUTED};
    border-color: {ACCENT_MUTED};
    color: #ffffff;
}}
QPushButton#ghostButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_MUTED};
    padding: 7px 10px;
}}
QPushButton#ghostButton:hover {{
    background: #eef2f7;
    color: {TEXT};
}}
QPushButton#ghostButton:disabled {{
    background: transparent;
    color: #c3cbd8;
}}
QPushButton#dangerButton {{
    background: {SURFACE};
    border: 1px solid #f0cfcf;
    color: {DANGER};
}}
QPushButton#dangerButton:hover {{
    background: {DANGER_SOFT};
    border-color: #e6b3b3;
}}
QPushButton#dangerButton:disabled {{
    background: #f1f4f8;
    border-color: #e4e9f0;
    color: #c3cbd8;
}}
QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {ACCENT};
    font-weight: 600;
    padding: 4px 2px;
    text-align: left;
}}
QPushButton#linkButton:hover {{
    color: {ACCENT_HOVER};
    text-decoration: underline;
}}

/* ---------- 状态条 ---------- */
QFrame#statusBanner {{
    background: {ACCENT_SOFT};
    border-radius: 10px;
}}
QFrame#statusBanner[state="neutral"] {{
    background: #f1f4f8;
}}
QFrame#statusBanner[state="info"] {{
    background: {ACCENT_SOFT};
}}
QFrame#statusBanner[state="success"] {{
    background: {SUCCESS_SOFT};
}}
QFrame#statusBanner[state="warning"] {{
    background: {WARNING_SOFT};
}}
QFrame#statusBanner[state="error"] {{
    background: {DANGER_SOFT};
}}
QFrame#statusRail {{
    background: {ACCENT};
    border-radius: 2px;
}}
QFrame#statusRail[state="neutral"] {{ background: {TEXT_FAINT}; }}
QFrame#statusRail[state="info"] {{ background: {ACCENT}; }}
QFrame#statusRail[state="success"] {{ background: {SUCCESS}; }}
QFrame#statusRail[state="warning"] {{ background: {WARNING}; }}
QFrame#statusRail[state="error"] {{ background: {DANGER}; }}
QLabel#statusText {{
    font-size: 13px;
    color: {TEXT};
}}
QLabel#statusTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT};
}}
QFrame#statusDetail {{
    background: transparent;
}}

QProgressBar {{
    background: #e3e9f2;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}

/* ---------- 摘要卡片 ---------- */
QFrame#featureCard {{
    background: #fbfcfe;
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#featureCard[tone="add"] {{ border-left: 3px solid {SUCCESS}; }}
QFrame#featureCard[tone="delete"] {{ border-left: 3px solid {DANGER}; }}
QFrame#featureCard[tone="info"] {{ border-left: 3px solid {ACCENT}; }}
QLabel#featureTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#featureStatus {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}
QLabel#featureMetric {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* ---------- 问题表 ---------- */
QTableView {{
    background: {SURFACE};
    alternate-background-color: #fafbfd;
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTableView::item {{
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid #f1f4f8;
}}
QTableView::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: #f7f9fc;
    color: #475569;
    padding: 9px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: #f7f9fc;
    border: none;
}}
QLabel#emptyHint {{
    color: {TEXT_FAINT};
    font-size: 13px;
}}

/* ---------- 高级信息 ---------- */
QToolButton#disclosure {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    font-weight: 600;
    padding: 4px 2px;
    text-align: left;
}}
QToolButton#disclosure:hover {{
    color: {ACCENT};
}}
QFrame#advancedPanel {{
    background: #f7f9fc;
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #aab6c6;
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
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #aab6c6;
}}

/* ---------- 对话框 ---------- */
QMessageBox {{
    background: {SURFACE};
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
QToolTip {{
    background: #0f172a;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}}
"""
