"""桌面端可复用的展示组件。

这些组件只负责外观与排版，不持有业务状态；业务状态仍由 ViewModel 统一提供。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .styles import THEME_LABELS

FILTER_ITEMS = (
    ("全部", "ALL"),
    ("错误", "ERROR"),
    ("警告", "WARNING"),
    ("提示", "INFO"),
    ("保留决定", "DECISION"),
)


class FileDropEdit(QLineEdit):
    """只接收一个本地文件，并把路径交给 ViewModel 的统一入口。"""

    path_dropped = Signal(str)

    def __init__(self, suffix: str, parent=None) -> None:
        super().__init__(parent)
        self._suffix = suffix
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == self._suffix:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        self.path_dropped.emit(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


class StepBadge(QLabel):
    """步骤序号徽标。"""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("stepBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(26, 26)


class SectionCard(QFrame):
    """带标题行的白色卡片容器。

    标题行由可选的步骤徽标、标题和右侧说明组成；内容放入 ``body`` 布局。
    """

    def __init__(self, title: str, *, step: str | None = None, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 15, 18, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        if step:
            header.addWidget(StepBadge(step))
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        header.addWidget(title_label)
        header.addStretch(1)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("sectionHint")
            header.addWidget(hint_label)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)


class StatusBanner(QFrame):
    """状态条：左侧色条 + 状态标题 + 补充说明。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(11)

        self.rail = QFrame()
        self.rail.setObjectName("statusRail")
        self.rail.setFixedSize(4, 20)
        layout.addWidget(self.rail, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("statusTitle")
        self.detail = QLabel()
        self.detail.setObjectName("mutedValue")
        self.detail.setWordWrap(True)
        text_box.addWidget(self.title)
        text_box.addWidget(self.detail)
        layout.addLayout(text_box, 1)

        self.counter = QLabel()
        self.counter.setObjectName("stepCounter")
        layout.addWidget(self.counter, 0, Qt.AlignVCenter)
        self.set_state("info")
        self.set_message("等待输入")
        self.set_step(1, 3)

    def set_state(self, state: str) -> None:
        """切换状态配色：neutral / info / success / warning / error。"""
        for widget in (self, self.rail):
            widget.setProperty("state", state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_message(self, title: str, detail: str = "") -> None:
        """更新状态文案。"""
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))

    def set_step(self, current: int, total: int) -> None:
        """更新流水线步骤指示。"""
        self.counter.setText(f"STEP {current} / {total}")


class FileSlot(QFrame):
    """紧凑文件槽：图标 + 标题 + 可编辑路径 + 浏览/清除，支持拖入文件。"""

    path_dropped = Signal(str)
    browse_requested = Signal()
    clear_requested = Signal()

    def __init__(self, title: str, suffix: str, glyph: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fileSlot")
        self.setAcceptDrops(True)
        self._suffix = suffix

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel(glyph)
        icon.setObjectName("fileSlotIcon")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("fileSlotTitle")
        suffix_chip = QLabel(suffix)
        suffix_chip.setObjectName("fileSlotSuffix")
        self.ready_chip = QLabel("已就绪")
        self.ready_chip.setObjectName("readyChip")
        self.ready_chip.setVisible(False)
        head.addWidget(title_label)
        head.addWidget(suffix_chip)
        head.addWidget(self.ready_chip)
        head.addStretch(1)
        text_box.addLayout(head)

        self.edit = FileDropEdit(suffix)
        self.edit.setObjectName("fileSlotPath")
        self.edit.setPlaceholderText("选择或拖入文件")
        text_box.addWidget(self.edit)
        layout.addLayout(text_box, 1)

        browse = QPushButton("浏览…")
        browse.clicked.connect(self.browse_requested)
        clear = QPushButton("清除")
        clear.setObjectName("ghostButton")
        clear.clicked.connect(self.clear_requested)
        layout.addWidget(browse, 0, Qt.AlignTop)
        layout.addWidget(clear, 0, Qt.AlignTop)

    def set_ready(self, ready: bool) -> None:
        """显示或隐藏“已就绪”徽标。"""
        self.ready_chip.setVisible(ready)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        suffixes = {Path(url.toLocalFile()).suffix.lower() for url in urls if url.isLocalFile()}
        if suffixes & {self._suffix}:
            self.setProperty("dragover", "true")
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragover", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragover", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() == self._suffix:
                self.path_dropped.emit(path)
                break
        event.acceptProposedAction()


class LegacyNotice(QFrame):
    """原版单栏长条模式的对比提示条。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("legacyNotice")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(10)
        text = QLabel(
            "正在演示【原版单列长条模式】：注意观察下方输入框与搜索框被拉长到整个屏幕宽度，"
            "眼动跨度极大，且下方校验区被严重挤压。"
        )
        text.setObjectName("legacyNoticeText")
        text.setWordWrap(True)
        layout.addWidget(text, 1)
        self.back_button = QPushButton("切回双栏紧凑布局")
        self.back_button.setObjectName("linkButton")
        layout.addWidget(self.back_button, 0, Qt.AlignVCenter)


class PillButton(QFrame):
    """带计数的胶囊按钮。"""

    clicked = Signal()

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("filterPill")
        self.setProperty("checked", "false")
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(6)
        self.name = QLabel(label)
        self.name.setObjectName("pillName")
        self.count = QLabel("0")
        self.count.setObjectName("filterCount")
        layout.addWidget(self.name)
        layout.addWidget(self.count)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()
        super().mousePressEvent(event)

    def set_checked(self, checked: bool) -> None:
        self.setProperty("checked", "true" if checked else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_count(self, count: int) -> None:
        self.count.setText(str(count))


class SegmentedFilter(QWidget):
    """按级别筛选问题的胶囊分段，带实时计数。"""

    severity_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("filterPills")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._pills: dict[str, PillButton] = {}
        for label, value in FILTER_ITEMS:
            pill = PillButton(label)
            pill.clicked.connect(lambda value=value: self._select(value))
            layout.addWidget(pill)
            self._pills[value] = pill
        self._pills["ALL"].set_checked(True)
        self._value = "ALL"

    def _select(self, value: str) -> None:
        self._value = value
        for name, pill in self._pills.items():
            pill.set_checked(name == value)
        self.severity_changed.emit(value)

    def set_counts(self, counts: dict[str, int]) -> None:
        """更新各分类计数。"""
        for value, pill in self._pills.items():
            pill.set_count(counts.get(value, 0))

    def value(self) -> str:
        return self._value


class ThemeSwitch(QWidget):
    """白天 / 夜间主题切换控件。"""

    theme_changed = Signal(str)

    def __init__(self, theme: str = "light", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("themeSwitch")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        self._theme = "light"
        self._buttons: dict[str, QPushButton] = {}
        for name, label in THEME_LABELS.items():
            button = QPushButton(label)
            button.setObjectName("themeSegment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(26)
            button.clicked.connect(lambda _checked=False, value=name: self._select(value))
            layout.addWidget(button)
            self._buttons[name] = button
        self.set_theme(theme)

    def _select(self, theme: str) -> None:
        self.set_theme(theme)
        self.theme_changed.emit(theme)

    def set_theme(self, theme: str) -> None:
        """高亮当前主题，不触发信号。"""
        self._theme = theme if theme in THEME_LABELS else "light"
        for name, button in self._buttons.items():
            button.setChecked(name == self._theme)

    def theme(self) -> str:
        return self._theme
