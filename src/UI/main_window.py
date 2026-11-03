"""DaVinci 网关路由工具的单窗口 Qt Widgets 界面。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from davinci_gw.contracts import FeatureSummaryDto

from . import __version__
from .components import SectionCard, StatusBanner, ThemeSwitch
from .detail_dialog import FeatureDetailDialog
from .issue_model import IssueFilterProxyModel, IssueTableModel
from .logging_config import log_path
from .state import GuiState
from .styles import apply_theme, detect_system_theme
from .view_model import GatewayViewModel


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


class MainWindow(QMainWindow):
    """把四步工作流、结果和问题集中在一个可滚动窗口。"""

    def __init__(self, view_model: GatewayViewModel) -> None:
        super().__init__()
        self.vm = view_model
        if not QCoreApplication.organizationName():
            # 窗口位置、主题等设置需要稳定的组织名与应用名，入口未设置时在此兜底。
            QCoreApplication.setOrganizationName("DaVinciGW")
            QCoreApplication.setApplicationName("DaVinciGW")
        self.settings = QSettings()
        self._allow_close = False
        self._closing = False
        self._detail_dialog: FeatureDetailDialog | None = None
        self._theme = str(self.settings.value("ui/theme", "") or "") or detect_system_theme()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme)
        self.setWindowTitle("DaVinci 网关路由工具")
        self.setMinimumSize(1000, 700)
        self.resize(1240, 880)
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect()
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._rebuild_summary()
        self._sync()

    # ------------------------------------------------------------------ 布局

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("pageScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("pageContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(26, 22, 26, 24)
        root.setSpacing(16)

        root.addWidget(self._build_header())

        inputs = SectionCard("选择输入文件", step="1", hint="可直接拖入文件")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.config_edit = FileDropEdit(".xlsx")
        self.config_edit.setPlaceholderText("选择或拖入标准配置表（.xlsx）")
        self.config_edit.setAccessibleName("标准配置表路径")
        self.config_button = QPushButton("浏览…")
        self.config_clear = QPushButton("清除")
        self.config_clear.setObjectName("ghostButton")
        self.baseline_edit = FileDropEdit(".arxml")
        self.baseline_edit.setPlaceholderText("选择或拖入基准 ARXML（.arxml）")
        self.baseline_edit.setAccessibleName("基准 ARXML 路径")
        self.baseline_button = QPushButton("浏览…")
        self.baseline_clear = QPushButton("清除")
        self.baseline_clear.setObjectName("ghostButton")
        self._add_file_row(grid, 0, "标准配置表", self.config_edit, self.config_button, self.config_clear)
        self._add_file_row(grid, 1, "基准 ARXML", self.baseline_edit, self.baseline_button, self.baseline_clear)
        grid.setColumnStretch(1, 1)
        inputs.body.addLayout(grid)
        input_hint = QLabel(
            "标准配置表需符合本项目的输入契约（*_vX.x.xlsx）；"
            "基准 ARXML 需包含 CanIf、EcuC、PduR，信号路由还需要 Com。"
        )
        input_hint.setObjectName("fieldHint")
        input_hint.setWordWrap(True)
        inputs.body.addWidget(input_hint)
        root.addWidget(inputs)

        actions = SectionCard("预览并生成", step="2", hint="先预览并确认，再生成新文件")
        action_layout = QGridLayout()
        action_layout.setHorizontalSpacing(12)
        action_layout.setVerticalSpacing(10)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("预览通过后自动建议输出路径")
        self.output_edit.setAccessibleName("输出 ARXML 路径")
        self.output_button = QPushButton("选择输出…")
        output_label = QLabel("输出文件")
        output_label.setObjectName("fieldLabel")
        output_label.setMinimumWidth(96)
        output_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        action_layout.addWidget(output_label, 0, 0)
        action_layout.addWidget(self.output_edit, 0, 1)
        action_layout.addWidget(self.output_button, 0, 2)
        self.output_error = QLabel()
        self.output_error.setObjectName("outputError")
        self.output_error.setWordWrap(True)
        action_layout.addWidget(self.output_error, 1, 1, 1, 2)
        self.preview_button = QPushButton("预览变更")
        self.generate_button = QPushButton("生成 ARXML")
        self.generate_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("dangerButton")
        action_buttons = QHBoxLayout()
        action_buttons.setSpacing(10)
        action_buttons.addStretch(1)
        action_buttons.addWidget(self.cancel_button)
        action_buttons.addWidget(self.preview_button)
        action_buttons.addWidget(self.generate_button)
        action_layout.addLayout(action_buttons, 2, 1, 1, 2)
        action_layout.setColumnStretch(1, 1)
        actions.body.addLayout(action_layout)
        root.addWidget(actions)

        self.status_banner = StatusBanner()
        root.addWidget(self.status_banner)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        root.addWidget(self.progress)

        self.result_group = SectionCard("生成结果")
        result_layout = QHBoxLayout()
        result_layout.setSpacing(10)
        self.result_path = QLabel()
        self.result_path.setObjectName("monoValue")
        self.result_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_path.setWordWrap(True)
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.copy_path_button = QPushButton("复制路径")
        result_layout.addWidget(self.result_path, 1)
        result_layout.addWidget(self.open_folder_button)
        result_layout.addWidget(self.copy_path_button)
        self.result_group.body.addLayout(result_layout)
        root.addWidget(self.result_group)

        self.check_group = SectionCard("输入检查")
        self.check_layout = QGridLayout()
        self.check_layout.setHorizontalSpacing(18)
        self.check_layout.setVerticalSpacing(8)
        self.check_layout.setColumnStretch(0, 0)
        self.check_layout.setColumnStretch(1, 1)
        self.check_group.body.addLayout(self.check_layout)
        root.addWidget(self.check_group)

        self.feature_group = SectionCard("变更摘要")
        self.feature_layout = QGridLayout()
        self.feature_layout.setHorizontalSpacing(12)
        self.feature_layout.setVerticalSpacing(12)
        self.feature_group.body.addLayout(self.feature_layout)
        root.addWidget(self.feature_group)

        issues = SectionCard("问题与保留决定", hint="错误会阻止生成；警告与保留决定需要人工确认")
        issue_layout = QVBoxLayout()
        issue_layout.setSpacing(10)
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.severity_filter = QComboBox()
        for label, value in (("全部", "ALL"), ("错误", "ERROR"), ("警告", "WARNING"),
                             ("提示", "INFO"), ("保留决定", "DECISION")):
            self.severity_filter.addItem(label, value)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索代码、说明、位置或建议")
        self.copy_issues_button = QPushButton("复制所选")
        filters.addWidget(self.severity_filter)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.copy_issues_button)
        issue_layout.addLayout(filters)
        self.issue_model = IssueTableModel(self)
        self.issue_proxy = IssueFilterProxyModel(self)
        self.issue_proxy.setSourceModel(self.issue_model)
        self.issue_table = QTableView()
        self.issue_table.setModel(self.issue_proxy)
        self.issue_table.setSortingEnabled(True)
        self.issue_table.setSelectionBehavior(QTableView.SelectRows)
        self.issue_table.setShowGrid(False)
        self.issue_table.setAlternatingRowColors(True)
        self.issue_table.setMinimumHeight(200)
        header = self.issue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for column, width in ((1, 230), (2, 190), (3, 190), (5, 180)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.issue_table.setColumnWidth(column, width)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.issue_table.verticalHeader().setVisible(False)
        self.issue_table.verticalHeader().setDefaultSectionSize(30)
        issue_layout.addWidget(self.issue_table)
        self.issue_empty = QLabel("暂无问题。预览完成后，错误、警告与保留决定会显示在这里。")
        self.issue_empty.setObjectName("emptyHint")
        self.issue_empty.setAlignment(Qt.AlignCenter)
        issue_layout.addWidget(self.issue_empty)
        issues.body.addLayout(issue_layout)
        root.addWidget(issues)

        self.advanced_toggle = QPushButton("展开高级信息")
        self.advanced_toggle.setObjectName("linkButton")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setCursor(Qt.PointingHandCursor)
        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("advancedPanel")
        advanced_layout = QGridLayout()
        advanced_layout.setContentsMargins(14, 12, 14, 12)
        advanced_layout.setHorizontalSpacing(18)
        advanced_layout.setVerticalSpacing(8)
        self.operation_label = QLabel("—")
        self.session_label = QLabel("—")
        self.version_label = QLabel(__version__)
        self.operation_label.setObjectName("monoValue")
        self.session_label.setObjectName("monoValue")
        self.open_log_button = QPushButton("打开日志目录")
        self.open_log_button.setObjectName("linkButton")
        for row, (caption, value) in enumerate((
            ("操作 ID", self.operation_label),
            ("会话 ID", self.session_label),
            ("版本", self.version_label),
        )):
            label = QLabel(caption)
            label.setObjectName("mutedValue")
            advanced_layout.addWidget(label, row, 0)
            advanced_layout.addWidget(value, row, 1)
        advanced_layout.addWidget(self.open_log_button, 3, 1)
        advanced_layout.setColumnStretch(1, 1)
        self.advanced_panel.setLayout(advanced_layout)
        self.advanced_panel.setVisible(False)
        root.addWidget(self.advanced_toggle)
        root.addWidget(self.advanced_panel)
        root.addStretch(1)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)

        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.vm.start_preview)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self.vm.start_generate)
        QShortcut(QKeySequence("Esc"), self, activated=self.vm.cancel)

    def _build_header(self) -> QWidget:
        """页头：标题、说明与版本标识。"""
        header = QWidget()
        header.setObjectName("pageHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title = QLabel("DaVinci 网关路由配置生成")
        title.setObjectName("pageTitle")
        subtitle = QLabel("选择标准配置表和基准 ARXML，先预览，再生成新文件。")
        subtitle.setObjectName("pageSubtitle")
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        layout.addLayout(text_box)
        layout.addStretch(1)
        self.theme_switch = ThemeSwitch(self._theme)
        layout.addWidget(self.theme_switch)
        version_chip = QLabel(f"v{__version__}")
        version_chip.setObjectName("versionChip")
        local_chip = QLabel("本地运行")
        local_chip.setObjectName("softChip")
        layout.addWidget(version_chip)
        layout.addWidget(local_chip)
        return header

    @staticmethod
    def _add_file_row(grid, row: int, caption: str, edit, browse, clear) -> None:
        """按统一的标签、输入框和按钮样式排一行文件输入。"""
        label = QLabel(caption)
        label.setObjectName("fieldLabel")
        label.setMinimumWidth(96)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(label, row, 0)
        grid.addWidget(edit, row, 1)
        grid.addWidget(browse, row, 2)
        grid.addWidget(clear, row, 3)

    # ------------------------------------------------------------------ 连接

    def _connect(self) -> None:
        self.vm.changed.connect(self._sync)
        self.vm.issues_changed.connect(self.issue_model.set_issues)
        self.vm.preview_changed.connect(self._rebuild_summary)
        self.vm.shutdown_finished.connect(self._finish_close)
        self.vm.doip_choice_required.connect(self._choose_doip_prerequisites)
        self.config_button.clicked.connect(lambda: self._browse_input("config"))
        self.baseline_button.clicked.connect(lambda: self._browse_input("baseline"))
        self.config_clear.clicked.connect(lambda: self.vm.set_config_path(""))
        self.baseline_clear.clicked.connect(lambda: self.vm.set_baseline_path(""))
        self.config_edit.path_dropped.connect(self.vm.set_config_path)
        self.baseline_edit.path_dropped.connect(self.vm.set_baseline_path)
        self.config_edit.editingFinished.connect(lambda: self.vm.set_config_path(self.config_edit.text()))
        self.baseline_edit.editingFinished.connect(lambda: self.vm.set_baseline_path(self.baseline_edit.text()))
        self.output_edit.textEdited.connect(lambda text: self.vm.set_output_path(text, manual=True))
        self.output_button.clicked.connect(self._browse_output)
        self.preview_button.clicked.connect(self.vm.start_preview)
        self.generate_button.clicked.connect(self.vm.start_generate)
        self.cancel_button.clicked.connect(self.vm.cancel)
        self.severity_filter.currentIndexChanged.connect(
            lambda: self.issue_proxy.set_severity(self.severity_filter.currentData())
        )
        self.search_edit.textChanged.connect(self.issue_proxy.set_search)
        self.copy_issues_button.clicked.connect(self._copy_issues)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.theme_switch.theme_changed.connect(self._apply_theme)
        self.open_folder_button.clicked.connect(self._open_artifact_folder)
        self.copy_path_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.vm.artifact_path))
        self.open_log_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path().parent))))

    def _choose_doip_prerequisites(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("DoIP→CAN 前置缺失")
        dialog.setText("选中映射缺少 CAN 诊断前置。请查看问题清单并选择本次处理方式。")
        dialog.setDetailedText("\n".join(issue.message for issue in self.vm.issues if issue.code == "DOIP_PREREQUISITE_MISSING"))
        block = dialog.addButton("A 阻断整个本次生成", QMessageBox.RejectRole)
        skip = dialog.addButton("B 跳过前置缺失映射", QMessageBox.AcceptRole)
        dialog.addButton("C 其他处理，返回修改输入", QMessageBox.ActionRole)
        dialog.setDefaultButton(block)
        dialog.exec()
        if dialog.clickedButton() is skip:
            self.vm.choose_doip_missing_policy("SKIP")
        elif dialog.clickedButton() is block:
            self.vm.choose_doip_missing_policy("BLOCK")

    def _browse_input(self, role: str) -> None:
        recent = str(self.settings.value(f"recent/{role}", ""))
        filter_text = "Excel 配置表 (*.xlsx)" if role == "config" else "AUTOSAR XML (*.arxml)"
        path, _ = QFileDialog.getOpenFileName(self, "选择输入文件", recent, filter_text)
        if not path:
            return
        self.settings.setValue(f"recent/{role}", str(Path(path).parent))
        (self.vm.set_config_path if role == "config" else self.vm.set_baseline_path)(path)

    def _browse_output(self) -> None:
        start = self.vm.output_path or str(self.settings.value("recent/output", ""))
        path, _ = QFileDialog.getSaveFileName(self, "选择输出文件", start, "AUTOSAR XML (*.arxml)")
        if path:
            if not path.lower().endswith(".arxml"):
                path += ".arxml"
            self.settings.setValue("recent/output", str(Path(path).parent))
            self.vm.set_output_path(path, manual=True)

    # ------------------------------------------------------------------ 同步

    def _sync(self) -> None:
        controls = self.vm.controls
        if self.config_edit.text() != self.vm.config_path:
            self.config_edit.setText(self.vm.config_path)
        if self.baseline_edit.text() != self.vm.baseline_path:
            self.baseline_edit.setText(self.vm.baseline_path)
        if self.output_edit.text() != self.vm.output_path:
            self.output_edit.setText(self.vm.output_path)
        for widget in (self.config_edit, self.config_button, self.config_clear,
                       self.baseline_edit, self.baseline_button, self.baseline_clear):
            widget.setEnabled(controls.inputs_enabled)
        self.output_edit.setEnabled(controls.inputs_enabled)
        self.output_button.setEnabled(controls.inputs_enabled)
        self.preview_button.setEnabled(controls.preview_enabled)
        self.generate_button.setEnabled(controls.generate_enabled)
        self.cancel_button.setEnabled(controls.cancel_enabled)
        tone, fallback_title = {
            GuiState.EMPTY: ("neutral", "等待输入"),
            GuiState.READY: ("info", "输入就绪"),
            GuiState.PREPARING: ("info", "正在预览"),
            GuiState.PREVIEW_VALID: ("success", "预览通过"),
            GuiState.PREVIEW_INVALID: ("warning", "预览未通过"),
            GuiState.GENERATING: ("info", "正在生成"),
            GuiState.SUCCESS: ("success", "生成成功"),
            GuiState.FAILED: ("error", "操作失败"),
            GuiState.CANCELLED: ("warning", "操作已取消"),
        }[self.vm.state]
        self.status_banner.set_state(tone)
        self.status_banner.set_message(self.vm.stage_name or fallback_title)
        self.progress.setValue(self.vm.progress_percent)
        self.progress.setVisible(self.vm.state in {GuiState.PREPARING, GuiState.GENERATING})
        self.output_error.setText(self.vm.output_error)
        self.output_error.setVisible(bool(self.vm.output_error))
        self.result_group.setVisible(bool(self.vm.artifact_path))
        self.result_path.setText(self.vm.artifact_path)
        self.operation_label.setText(self.vm.operation_id or "—")
        self.session_label.setText(self.vm.session_id or "—")
        has_issues = self.issue_model.rowCount() > 0
        self.issue_table.setVisible(has_issues)
        self.issue_empty.setVisible(not has_issues)
        self.copy_issues_button.setEnabled(has_issues)

    def _rebuild_summary(self) -> None:
        self._clear_layout(self.check_layout)
        row = 0
        for input_file in self.vm.input_files:
            size = input_file.fingerprint.size if input_file.fingerprint else 0
            self._add_check_row(row, "配置表" if input_file.role == "CONFIG" else "基准 ARXML",
                                f"{Path(input_file.path).name} · {size / 1024 / 1024:.2f} MB", tone="mono")
            row += 1
        if self.vm.target_version:
            self._add_check_row(row, "目标版本", self.vm.target_version)
            row += 1
        for check in self.vm.checks:
            self._add_check_row(row, check.display_name, check.detail or check.status, tone="ok")
            row += 1
        self.check_group.setVisible(row > 0)

        self._clear_layout(self.feature_layout)
        for index, feature in enumerate(self.vm.features):
            card = QFrame()
            card.setObjectName("featureCard")
            card.setProperty("tone", self._feature_tone(feature))
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(6)
            heading = QHBoxLayout()
            heading.setSpacing(8)
            title = QLabel(feature.display_name)
            title.setObjectName("featureTitle")
            heading.addWidget(title)
            heading.addStretch(1)
            status = QLabel(feature.status)
            status.setObjectName("featureStatus")
            heading.addWidget(status)
            layout.addLayout(heading)
            for metric in feature.metrics:
                value = QLabel(f"{metric.label}：{metric.value}")
                value.setObjectName("featureMetric")
                layout.addWidget(value)
            if feature.details:
                detail_button = QPushButton("查看详情")
                detail_button.setObjectName("linkButton")
                detail_button.setAccessibleName(f"查看{feature.display_name}详情")
                detail_button.clicked.connect(
                    lambda _checked=False, item=feature: self._show_feature_details(item),
                )
                layout.addWidget(detail_button)
            self.feature_layout.addWidget(card, index // 2, index % 2)
        self.feature_group.setVisible(bool(self.vm.features))

    def _add_check_row(self, row: int, caption: str, value: str, *, tone: str = "") -> None:
        """输入检查的一行：左侧说明 + 右侧取值。"""
        label = QLabel(caption)
        label.setObjectName("mutedValue")
        content = QLabel(value)
        content.setObjectName({"mono": "monoValue", "ok": "checkValue"}.get(tone, "checkPlain"))
        self.check_layout.addWidget(label, row, 0)
        self.check_layout.addWidget(content, row, 1)

    @staticmethod
    def _feature_tone(feature: FeatureSummaryDto) -> str:
        """按变更类型给摘要卡片着色。"""
        actions = {detail.action for detail in feature.details}
        if "DELETE" in actions:
            return "delete"
        if "ADD" in actions:
            return "add"
        return "info"

    def _show_feature_details(self, feature: FeatureSummaryDto) -> None:
        if self._detail_dialog is not None:
            self._detail_dialog.close()
        self._detail_dialog = FeatureDetailDialog(feature, self)
        self._detail_dialog.show()
        self._detail_dialog.raise_()
        self._detail_dialog.activateWindow()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _copy_issues(self) -> None:
        rows = {self.issue_proxy.mapToSource(index).row() for index in self.issue_table.selectionModel().selectedRows()}
        text = self.issue_model.copy_text(rows)
        if text:
            QApplication.clipboard().setText(text)

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_toggle.setText("收起高级信息" if checked else "展开高级信息")
        self.advanced_panel.setVisible(checked)

    def _apply_theme(self, theme: str) -> None:
        """切换白天 / 夜间主题，并记住用户的选择。"""
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self.settings.setValue("ui/theme", theme)

    def _open_artifact_folder(self) -> None:
        if self.vm.artifact_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.vm.artifact_path).parent)))

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        suffixes = {Path(url.toLocalFile()).suffix.lower() for url in event.mimeData().urls() if url.isLocalFile()}
        if suffixes & {".xlsx", ".arxml"}:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            suffix = Path(path).suffix.lower()
            if suffix == ".xlsx":
                self.vm.set_config_path(path)
            elif suffix == ".arxml":
                self.vm.set_baseline_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close:
            self.settings.setValue("window/geometry", self.saveGeometry())
            event.accept()
            return
        if self._closing:
            event.ignore()
            return
        if self.vm.runner.is_busy:
            answer = QMessageBox.question(
                self,
                "正在处理",
                "当前操作尚未完成。是否安全取消并退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self._closing = True
        self.setEnabled(False)
        self.vm.shutdown()
        event.ignore()

    def _finish_close(self) -> None:
        self._allow_close = True
        self.close()
