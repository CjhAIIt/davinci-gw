"""桌面端可复用的展示组件。

这些组件只负责外观与排版，不持有业务状态；业务状态仍由 ViewModel 统一提供。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


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
        self.set_state("info")
        self.set_message("等待输入")

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
