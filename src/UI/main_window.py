"""DaVinci 网关路由工具的单窗口 Qt Widgets 界面。

窗口采用应用壳层结构：顶部全宽导航栏、左侧输入侧栏、右侧校验工作台、底部全宽状态栏。
界面只做展示与编排，业务规则全部来自 ViewModel 与核心。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
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
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from davinci_gw.contracts import FeatureSummaryDto

from . import __version__
from .components import (
    BrandLogoWidget,
    FileDropEdit,
    FileSlot,
    GridCanvasWidget,
    InfoIconWidget,
    LegacyNotice,
    SectionCard,
    SegmentedFilter,
    StatusBanner,
    ThemeSwitch,
    make_icon,
)
from .detail_dialog import FeatureDetailDialog, IssueDetailDialog
from .issue_model import IssueFilterProxyModel, IssueTableDelegate, IssueTableModel
from .logging_config import log_path
from .state import GuiState
from .styles import THEMES, apply_theme, detect_system_theme
from .view_model import GatewayViewModel

LAYOUT_BENTO = "bento"
LAYOUT_LEGACY = "legacy"

SIDEBAR_WIDTH = 470
ISSUE_ROW_HEIGHT = 68
ISSUE_MAX_VISIBLE_ROWS = 8


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
        self._issue_dialog: IssueDetailDialog | None = None
        self._theme = str(self.settings.value("ui/theme", "") or "") or detect_system_theme()
        self._layout_mode = LAYOUT_BENTO
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme)
        self.setWindowTitle("DaVinci 网关路由工具")
        self.setMinimumSize(1080, 680)
        self.resize(1440, 900)
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
        shell = QWidget()
        shell.setObjectName("appShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        shell_layout.addWidget(self._build_header())

        self._mode_stack = QStackedWidget()
        self._mode_stack.setObjectName("bentoColumn")
        shell_layout.addWidget(self._mode_stack, 1)

        # 新版：左侧输入侧栏 + 右侧校验工作台。
        bento_host = QWidget()
        bento_host.setObjectName("bentoColumn")
        bento = QHBoxLayout(bento_host)
        bento.setContentsMargins(0, 0, 0, 0)
        bento.setSpacing(0)

        self.left_sidebar = QFrame()
        self.left_sidebar.setObjectName("leftSidebar")
        self.left_sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(self.left_sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        self.left_scroll = QScrollArea()
        self.left_scroll.setObjectName("leftScroll")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self._left_host = QWidget()
        self._left_host.setObjectName("bentoLeft")
        self._left = QVBoxLayout(self._left_host)
        self._left.setContentsMargins(16, 14, 16, 16)
        self._left.setSpacing(14)
        self.left_scroll.setWidget(self._left_host)
        sidebar_layout.addWidget(self.left_scroll)
        bento.addWidget(self.left_sidebar)

        self._right_area = QWidget()
        self._right_area.setObjectName("bentoRight")
        area_layout = QVBoxLayout(self._right_area)
        area_layout.setContentsMargins(0, 0, 0, 0)
        area_layout.setSpacing(0)
        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("pageScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        self._right_host = GridCanvasWidget()
        self._right = QVBoxLayout(self._right_host)
        self._right.setContentsMargins(20, 14, 20, 18)
        self._right.setSpacing(14)
        self.page_scroll.setWidget(self._right_host)
        area_layout.addWidget(self.page_scroll)
        bento.addWidget(self._right_area, 1)
        self._mode_stack.addWidget(bento_host)

        # 原版：单栏长条布局，用于对比查看。
        legacy_host = QWidget()
        legacy_host.setObjectName("bentoColumn")
        legacy_area = QVBoxLayout(legacy_host)
        legacy_area.setContentsMargins(0, 0, 0, 0)
        legacy_area.setSpacing(0)
        self.legacy_scroll = QScrollArea()
        self.legacy_scroll.setObjectName("pageScroll")
        self.legacy_scroll.setWidgetResizable(True)
        self.legacy_scroll.setFrameShape(QFrame.NoFrame)
        self._legacy_host = QWidget()
        self._legacy_host.setObjectName("bentoLeft")
        self._legacy = QVBoxLayout(self._legacy_host)
        self._legacy.setContentsMargins(24, 18, 24, 18)
        self._legacy.setSpacing(14)
        self.legacy_scroll.setWidget(self._legacy_host)
        legacy_area.addWidget(self.legacy_scroll)
        self._mode_stack.addWidget(legacy_host)

        self.legacy_notice = LegacyNotice()
        self.legacy_notice.setVisible(False)
        self._legacy.insertWidget(0, self.legacy_notice)

        self.status_banner = StatusBanner()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)

        self._build_input_card()
        self._build_actions_card()
        self._build_result_card()
        self._build_check_card()
        self._build_feature_card()
        self._build_issues_card()
        self._build_telemetry_bar()
        self._set_layout_mode(LAYOUT_BENTO)

        shell_layout.addWidget(self._telemetry_bar)
        self.setCentralWidget(shell)

        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.vm.start_preview)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self.vm.start_generate)
        QShortcut(QKeySequence("Esc"), self, activated=self.vm.cancel)

    def _build_header(self) -> QWidget:
        """顶部全宽导航栏：品牌标识、标题、说明与右侧操作。"""
        header = QFrame()
        header.setObjectName("topHeaderBar")
        header.setFixedHeight(66)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)

        self.brand_logo = BrandLogoWidget()
        layout.addWidget(self.brand_logo, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("DaVinci 网关路由配置生成")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        version_chip = QLabel(f"v{__version__}")
        version_chip.setObjectName("versionChip")
        version_chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_row.addWidget(version_chip)
        local_chip = QLabel("本地运行")
        local_chip.setObjectName("readyChip")
        local_chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_row.addWidget(local_chip)
        title_row.addStretch(1)
        text_box.addLayout(title_row)
        subtitle = QLabel("选择标准配置表和基准 ARXML，先预览校验差异，确认无误后再生成新文件。")
        subtitle.setObjectName("pageSubtitle")
        text_box.addWidget(subtitle)
        layout.addLayout(text_box, 1)

        divider = QFrame()
        divider.setObjectName("headerDivider")
        divider.setFixedWidth(1)
        divider.setFixedHeight(28)
        layout.addWidget(divider, 0, Qt.AlignVCenter)

        self.demo_button = QPushButton("一键填入测试数据并预览")
        self.demo_button.setObjectName("demoChip")
        self.demo_button.setCursor(Qt.PointingHandCursor)
        self.demo_button.setVisible(self._demo_files() is not None)
        layout.addWidget(self.demo_button, 0, Qt.AlignVCenter)

        self.layout_toggle = QPushButton("当前：双栏紧凑布局（点击对比原版长条）")
        self.layout_toggle.setObjectName("chipButton")
        self.layout_toggle.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.layout_toggle, 0, Qt.AlignVCenter)

        self.theme_switch = ThemeSwitch(self._theme)
        layout.addWidget(self.theme_switch, 0, Qt.AlignVCenter)
        return header

    @staticmethod
    def _demo_files() -> tuple[Path, Path] | None:
        """开发环境下提供示例文件时返回它们，供一键预览使用。"""
        project = Path(__file__).resolve().parents[2]
        config = project / "input" / "网关路由配置表_v4.84.xlsx"
        baseline = project / "input" / "T13J.arxml"
        if config.is_file() and baseline.is_file():
            return config, baseline
        return None

    def _build_input_card(self) -> None:
        self._input_card = SectionCard(
            "选择输入文件", icon_kind="upload", inline_hint="支持拖入文件",
        )
        self.config_slot = FileSlot("标准配置表", ".xlsx")
        self.baseline_slot = FileSlot("基准 ARXML", ".arxml")
        self.config_edit = self.config_slot.edit
        self.baseline_edit = self.baseline_slot.edit
        self._input_card.body.addWidget(self.config_slot)
        self._input_card.body.addWidget(self.baseline_slot)

        callout = QFrame()
        callout.setObjectName("infoCallout")
        callout_layout = QHBoxLayout(callout)
        callout_layout.setContentsMargins(12, 10, 12, 10)
        callout_layout.setSpacing(9)
        callout_layout.addWidget(InfoIconWidget(), 0, Qt.AlignTop)
        hint = QLabel(
            "标准配置表需符合本项目的输入契约（*_vX.x.xlsx，支持 v4.83-4.85 区间命名）；"
            "基准 ARXML 需包含 CanIf、EcuC、PduR，信号路由还需要 Com。"
        )
        hint.setObjectName("fieldHint")
        hint.setWordWrap(True)
        callout_layout.addWidget(hint, 1)
        self._input_card.body.addWidget(callout)

    def _build_actions_card(self) -> None:
        self._actions_card = SectionCard(
            "预览并生成", icon_kind="bolt", hint="先预览并确认，再生成新文件",
        )
        layout = QVBoxLayout()
        layout.setSpacing(10)

        output_row = QVBoxLayout()
        output_row.setSpacing(6)
        output_label = QLabel("输出文件")
        output_label.setObjectName("fieldLabel")
        output_row.addWidget(output_label)
        output_path_row = QHBoxLayout()
        output_path_row.setSpacing(8)
        self.output_edit = QLineEdit()
        self.output_edit.setObjectName("outputPathEdit")
        self.output_edit.setPlaceholderText("预览通过后自动建议输出路径")
        self.output_edit.setAccessibleName("输出 ARXML 路径")
        output_path_row.addWidget(self.output_edit, 1)
        self.output_button = QPushButton("选择输出…")
        self.output_button.setCursor(Qt.PointingHandCursor)
        output_path_row.addWidget(self.output_button, 0)
        output_row.addLayout(output_path_row)
        layout.addLayout(output_row)

        self.output_error = QLabel()
        self.output_error.setObjectName("outputError")
        self.output_error.setWordWrap(True)
        self.output_error.setVisible(False)
        layout.addWidget(self.output_error)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.preview_button = QPushButton("预览变更")
        self.preview_button.setObjectName("previewButton")
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.generate_button = QPushButton("生成 ARXML")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.generate_button)
        layout.addLayout(buttons)

        self.gate_hint = QLabel()
        self.gate_hint.setObjectName("gateHint")
        self.gate_hint.setWordWrap(True)
        self.gate_hint.setVisible(False)
        layout.addWidget(self.gate_hint)

        self._actions_card.body.addLayout(layout)

    def _build_result_card(self) -> None:
        self.result_group = SectionCard("生成结果", icon_kind="folder")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        self.result_path = QLabel()
        self.result_path.setObjectName("monoValue")
        self.result_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_path.setWordWrap(True)
        layout.addWidget(self.result_path)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.copy_path_button = QPushButton("复制路径")
        self.copy_path_button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.open_folder_button)
        buttons.addWidget(self.copy_path_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.result_group.body.addLayout(layout)

    def _build_check_card(self) -> None:
        self.check_group = SectionCard("输入检查", icon_kind="pulse")
        self.check_layout = QVBoxLayout()
        self.check_layout.setSpacing(7)
        self.check_group.body.addLayout(self.check_layout)

    def _build_feature_card(self) -> None:
        self.feature_group = SectionCard("变更摘要", icon_kind="bolt")
        self.feature_layout = QVBoxLayout()
        self.feature_layout.setSpacing(10)
        self.feature_group.body.addLayout(self.feature_layout)

    def _build_issues_card(self) -> None:
        self._issues_card = SectionCard(
            "问题与保留决定", icon_kind="eye", hint="错误会阻止生成；警告与保留决定需人工确认",
        )
        layout = QVBoxLayout()
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.filter_pills = SegmentedFilter()
        toolbar.addWidget(self.filter_pills)
        toolbar.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchInput")
        self.search_edit.setPlaceholderText("搜索代码、说明、位置或建议")
        self.search_edit.setFixedWidth(240)
        self.copy_issues_button = QPushButton("复制所选")
        self.copy_issues_button.setCursor(Qt.PointingHandCursor)
        self.ack_button = QPushButton("批量确认")
        self.ack_button.setObjectName("ackBatchButton")
        self.ack_button.setCursor(Qt.PointingHandCursor)
        toolbar.addWidget(self.search_edit)
        toolbar.addWidget(self.copy_issues_button)
        toolbar.addWidget(self.ack_button)
        layout.addLayout(toolbar)

        self.issue_model = IssueTableModel(self)
        self.issue_proxy = IssueFilterProxyModel(self)
        self.issue_proxy.setSourceModel(self.issue_model)
        self.issue_table = QTableView()
        self.issue_table.setModel(self.issue_proxy)
        self.issue_delegate = IssueTableDelegate(self._theme, self.issue_table)
        self.issue_table.setItemDelegate(self.issue_delegate)
        self.issue_table.setSortingEnabled(True)
        self.issue_table.setSelectionBehavior(QTableView.SelectRows)
        self.issue_table.setShowGrid(False)
        self.issue_table.setAlternatingRowColors(False)
        self.issue_table.setMinimumHeight(260)
        header = self.issue_table.horizontalHeader()
        for column in (2, 3, 6):
            # 报文 ID、报文名称与处理建议已并入自绘单元格的副行，不再单列展示。
            self.issue_table.setColumnHidden(column, True)
        for column, width in ((0, 132), (1, 232), (5, 216), (7, 128)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.issue_table.setColumnWidth(column, width)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.issue_table.verticalHeader().setVisible(False)
        self.issue_table.verticalHeader().setDefaultSectionSize(68)
        list_frame = QFrame()
        list_frame.setObjectName("issueListFrame")
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.issue_table)

        self.issue_empty = QLabel("暂无问题。预览完成后，错误、警告与保留决定会显示在这里。")
        self.issue_empty.setObjectName("emptyHint")
        self.issue_empty.setAlignment(Qt.AlignCenter)
        list_layout.addWidget(self.issue_empty)
        layout.addWidget(list_frame)
        self._issues_card.body.addLayout(layout)

    def _build_telemetry_bar(self) -> None:
        """底部全宽状态条：操作 ID、会话 ID、版本与日志入口。"""
        self._telemetry_bar = QFrame()
        self._telemetry_bar.setObjectName("telemetryBar")
        layout = QHBoxLayout(self._telemetry_bar)
        layout.setContentsMargins(20, 7, 20, 7)
        layout.setSpacing(18)
        self.operation_label = QLabel("操作 ID —")
        self.session_label = QLabel("会话 ID —")
        self.version_label = QLabel(f"版本 {__version__}")
        for label in (self.operation_label, self.session_label, self.version_label):
            label.setObjectName("telemetryText")
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.open_log_button = QPushButton("打开日志目录")
        self.open_log_button.setObjectName("linkButton")
        for widget in (self.operation_label, self.session_label, self.version_label):
            layout.addWidget(widget, 1)
        layout.addWidget(self.open_log_button, 0)

    def _place(self, widget, layout) -> None:
        """把共享卡片放入指定布局。"""
        parent = widget.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().removeWidget(widget)
        widget.setParent(None)
        layout.addWidget(widget)
        widget.show()

    def _set_layout_mode(self, mode: str) -> None:
        """切换双栏紧凑布局与原版单栏长条布局。"""
        bento = mode == LAYOUT_BENTO
        left = self._left if bento else self._legacy
        right = self._right if bento else self._legacy
        for widget in (self._input_card, self._actions_card, self.result_group):
            self._place(widget, left)
        for widget in (self.status_banner, self.progress, self._issues_card, self.check_group,
                       self.feature_group):
            self._place(widget, right)
        if bento:
            self._left.addStretch(1)
            self._right.addStretch(1)
        else:
            self._legacy.addStretch(1)
        self._mode_stack.setCurrentIndex(0 if bento else 1)
        self._layout_mode = mode
        # 换布局会重新挂载卡片，这里恢复由业务状态决定的显隐，避免空卡片与残留进度条。
        self.result_group.setVisible(bool(self.vm.artifact_path))
        self.check_group.setVisible(bool(self.vm.input_files or self.vm.target_version or self.vm.checks))
        self.feature_group.setVisible(bool(self.vm.features))
        self.progress.setVisible(self.vm.state in {GuiState.PREPARING, GuiState.GENERATING})
        self.legacy_notice.setVisible(not bento)
        self.layout_toggle.setText(
            "当前：双栏紧凑布局（点击对比原版长条）" if bento
            else "当前：原版单栏长条（点击回到双栏紧凑布局）"
        )

    # ------------------------------------------------------------------ 连接

    def _connect(self) -> None:
        self.vm.changed.connect(self._sync)
        self.vm.issues_changed.connect(self._issue_model_changed)
        self.vm.preview_changed.connect(self._rebuild_summary)
        self.vm.shutdown_finished.connect(self._finish_close)
        self.vm.doip_choice_required.connect(self._choose_doip_prerequisites)
        self.config_slot.browse_requested.connect(lambda: self._browse_input("config"))
        self.baseline_slot.browse_requested.connect(lambda: self._browse_input("baseline"))
        self.config_slot.clear_requested.connect(lambda: self.vm.set_config_path(""))
        self.baseline_slot.clear_requested.connect(lambda: self.vm.set_baseline_path(""))
        self.config_slot.path_dropped.connect(self.vm.set_config_path)
        self.baseline_slot.path_dropped.connect(self.vm.set_baseline_path)
        # 文件槽内层输入框自己也能接收拖放，必须单独接线，否则拖到输入框无效。
        self.config_edit.path_dropped.connect(self.vm.set_config_path)
        self.baseline_edit.path_dropped.connect(self.vm.set_baseline_path)
        self.config_edit.editingFinished.connect(lambda: self.vm.set_config_path(self.config_edit.text()))
        self.baseline_edit.editingFinished.connect(lambda: self.vm.set_baseline_path(self.baseline_edit.text()))
        self.output_edit.textEdited.connect(lambda text: self.vm.set_output_path(text, manual=True))
        self.output_button.clicked.connect(self._browse_output)
        self.preview_button.clicked.connect(self.vm.start_preview)
        self.generate_button.clicked.connect(self.vm.start_generate)
        self.cancel_button.clicked.connect(self.vm.cancel)
        self.filter_pills.severity_changed.connect(self.issue_proxy.set_severity)
        self.filter_pills.severity_changed.connect(self._on_filter_changed)
        self.search_edit.textChanged.connect(self.issue_proxy.set_search)
        self.search_edit.textChanged.connect(lambda _text: self._on_filter_changed())
        self.copy_issues_button.clicked.connect(self._copy_issues)
        self.ack_button.clicked.connect(self._acknowledge_visible)
        self.issue_table.doubleClicked.connect(self._show_issue_details)
        self.issue_model.acknowledgement_changed.connect(self._sync_confirmation_state)
        self.layout_toggle.clicked.connect(self._toggle_layout)
        self.legacy_notice.back_button.clicked.connect(self._toggle_layout)
        self.demo_button.clicked.connect(self._load_demo)
        self.theme_switch.theme_changed.connect(self._apply_theme)
        self.open_folder_button.clicked.connect(self._open_artifact_folder)
        self.copy_path_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.vm.artifact_path))
        self.open_log_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path().parent))))
        self._refresh_icons()

    def _toggle_layout(self) -> None:
        self._set_layout_mode(LAYOUT_LEGACY if self._layout_mode == LAYOUT_BENTO else LAYOUT_BENTO)

    def _load_demo(self) -> None:
        """开发环境下填入示例输入并立即预览。"""
        files = self._demo_files()
        if files is None:
            return
        config, baseline = files
        self.vm.set_config_path(str(config))
        self.vm.set_baseline_path(str(baseline))
        self.vm.start_preview()

    def _issue_model_changed(self, issues) -> None:
        self.issue_model.set_issues(issues)
        self._refresh_filter_counts()
        self._sync_issue_table_height()

    def _sync_issue_table_height(self) -> None:
        """按可见问题条数调整表格高度，避免只露出两三行。"""
        rows = self.issue_proxy.rowCount()
        visible = min(max(rows, 1), ISSUE_MAX_VISIBLE_ROWS)
        header = self.issue_table.horizontalHeader().height() or 34
        self.issue_table.setFixedHeight(header + visible * ISSUE_ROW_HEIGHT + 2)

    def _on_filter_changed(self, *args) -> None:
        """级别筛选或搜索后同步表格高度。"""
        self._sync_issue_table_height()

    def _sync_confirmation_state(self) -> None:
        """把待确认数量同步给 ViewModel，作为生成的唯一门禁。"""
        self.vm.set_pending_confirmations(self.issue_model.pending_count())

    def _refresh_filter_counts(self) -> None:
        counts = {"ALL": self.issue_model.rowCount()}
        for row in range(self.issue_model.rowCount()):
            severity = str(self.issue_model.index(row, 0).data(Qt.UserRole) or "").upper()
            counts[severity] = counts.get(severity, 0) + 1
        self.filter_pills.set_counts(counts)

    def _visible_source_rows(self) -> list[int]:
        return [
            self.issue_proxy.mapToSource(self.issue_proxy.index(row, 0)).row()
            for row in range(self.issue_proxy.rowCount())
        ]

    def _acknowledge_visible(self) -> None:
        """把当前可见的警告与保留决定标记为已确认。"""
        changed = self.issue_model.acknowledge_all(self._visible_source_rows())
        self._refresh_filter_counts()
        self._sync()

    def _show_issue_details(self, index) -> None:
        """双击问题行查看完整定位与处理建议。"""
        source = self.issue_proxy.mapToSource(index)
        if not source.isValid():
            return
        row = source.row()
        issue = self.issue_model.issue_at(row)
        if issue is None:
            return
        if self._issue_dialog is not None:
            self._issue_dialog.close()
        self._issue_dialog = IssueDetailDialog(issue, self)
        self._issue_dialog.show()
        self._issue_dialog.raise_()
        self._issue_dialog.activateWindow()

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
        for widget in (self.config_slot, self.baseline_slot):
            widget.setEnabled(controls.inputs_enabled)
        self.config_slot.set_ready(bool(self.vm.config_path))
        self.baseline_slot.set_ready(bool(self.vm.baseline_path))
        self.output_edit.setEnabled(controls.inputs_enabled)
        self.output_button.setEnabled(controls.inputs_enabled)
        self.preview_button.setEnabled(controls.preview_enabled)
        pending = self.issue_model.pending_count()
        self.generate_button.setEnabled(controls.generate_enabled)
        self.generate_button.setToolTip(
            f"还有 {pending} 项警告或保留决定未确认，确认后才能生成" if pending else ""
        )
        self.gate_hint.setText(
            f"还有 {pending} 项警告或保留决定待确认，逐项确认后才能生成。" if pending else ""
        )
        self.gate_hint.setVisible(bool(pending))
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
        title = self.vm.stage_name or fallback_title
        detail = f"{pending} 项警告或保留决定待确认" if pending else ""
        self.status_banner.set_message(title, detail)
        self.status_banner.set_step(self._pipeline_step(), 3)
        self.progress.setValue(self.vm.progress_percent)
        self.progress.setVisible(self.vm.state in {GuiState.PREPARING, GuiState.GENERATING})
        self.output_error.setText(self.vm.output_error)
        self.output_error.setVisible(bool(self.vm.output_error))
        self.result_group.setVisible(bool(self.vm.artifact_path))
        self.result_path.setText(self.vm.artifact_path)
        self.operation_label.setText(f"操作 ID {self.vm.operation_id or '—'}")
        self.session_label.setText(f"会话 ID {self.vm.session_id or '—'}")
        has_issues = self.issue_model.rowCount() > 0
        self.issue_table.setVisible(has_issues)
        self.issue_empty.setVisible(not has_issues)
        self.copy_issues_button.setEnabled(has_issues)
        self.ack_button.setEnabled(has_issues)
        self._refresh_filter_counts()

    def _pipeline_step(self) -> int:
        """当前处于流程的第几步。"""
        if self.vm.state in {GuiState.PREPARING, GuiState.PREVIEW_VALID, GuiState.PREVIEW_INVALID}:
            return 2
        if self.vm.state in {GuiState.GENERATING, GuiState.SUCCESS, GuiState.FAILED, GuiState.CANCELLED}:
            return 3
        return 1

    def _rebuild_summary(self) -> None:
        self._clear_layout(self.check_layout)
        for input_file in self.vm.input_files:
            size = input_file.fingerprint.size if input_file.fingerprint else 0
            self._add_check_row(
                "配置表" if input_file.role == "CONFIG" else "基准 ARXML",
                f"{Path(input_file.path).name} · {size / 1024 / 1024:.2f} MB", tone="mono",
            )
        if self.vm.target_version:
            self._add_check_row("目标版本", self.vm.target_version)
        for check in self.vm.checks:
            self._add_check_row(check.display_name, check.detail or check.status, tone="ok")
        self.check_group.setVisible(bool(self.vm.input_files or self.vm.target_version or self.vm.checks))

        self._clear_layout(self.feature_layout)
        for feature in self.vm.features:
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
            self.feature_layout.addWidget(card)
        self.feature_group.setVisible(bool(self.vm.features))

    def _add_check_row(self, caption: str, value: str, *, tone: str = "") -> None:
        """输入检查的一行：左侧说明 + 右侧取值。"""
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(caption)
        label.setObjectName("mutedValue")
        label.setFixedWidth(112)
        content = QLabel(value)
        content.setObjectName({"mono": "monoValue", "ok": "checkValue"}.get(tone, "checkPlain"))
        content.setWordWrap(True)
        row.addWidget(label, 0, Qt.AlignTop)
        row.addWidget(content, 1)
        self.check_layout.addLayout(row)

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
            elif item.layout():
                child = item.layout()
                while child.count():
                    inner = child.takeAt(0)
                    if inner.widget():
                        inner.widget().deleteLater()

    def _copy_issues(self) -> None:
        rows = {self.issue_proxy.mapToSource(index).row() for index in self.issue_table.selectionModel().selectedRows()}
        text = self.issue_model.copy_text(rows)
        if text:
            QApplication.clipboard().setText(text)

    def _refresh_icons(self) -> None:
        """按当前主题刷新按钮图标。"""
        colors = THEMES.get(self._theme, THEMES["light"])
        self.preview_button.setIcon(make_icon("search", colors["accent"], 16))
        self.generate_button.setIcon(make_icon("play", colors["on_accent"], 16))
        self.output_button.setIcon(make_icon("folder", colors["button_fg"], 16))
        self.open_folder_button.setIcon(make_icon("folder", colors["accent"], 16))
        for button in (self.preview_button, self.generate_button, self.output_button,
                       self.open_folder_button):
            button.setIconSize(QSize(16, 16))

    def _apply_theme(self, theme: str) -> None:
        """切换白天 / 夜间主题，并记住用户的选择。"""
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self.settings.setValue("ui/theme", theme)
        self.config_slot.set_theme(theme)
        self.baseline_slot.set_theme(theme)
        self._right_host.set_theme(theme)
        self.issue_delegate.set_theme(theme)
        self.issue_table.viewport().update()
        self._refresh_icons()

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
