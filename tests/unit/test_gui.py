"""只覆盖 GUI 最关键的状态、动态展示和线程闭环。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from UI.components import PillButton
from UI.issue_model import IssueTableDelegate, IssueTableModel
from UI.main_window import MainWindow
from UI.output_paths import suggest_output_path, validate_output_path
from UI.state import GuiState, controls_for
from UI.task_runner import QtTaskRunner
from UI.view_model import GatewayViewModel
from davinci_gw.application.public_mapping import decisions_to_dto, issues_to_dto
from davinci_gw.contracts import ChangeDetailDto, FeatureSummaryDto, MetricDto, OperationStatus
from davinci_gw.domain.models import (
    RetentionDecision,
    SourceLocation,
    ValidationIssue,
    ValidationSeverity,
)
from davinci_gw.input.workbook_reader import read_workbook


class _FakeRunner(QObject):
    progress = Signal(object)
    preview_finished = Signal(object)
    generation_finished = Signal(object)
    stopped = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.discarded: list[str] = []
        self.commits: list[tuple[str, str, str]] = []

    def discard(self, session_id: str) -> None:
        self.discarded.append(session_id)

    def start_preview(self, task_id: str, config_path: str, baseline_path: str,
                      doip_missing_policy: str | None = None) -> None:
        pass

    def start_commit(self, task_id: str, session_id: str, output_path: str) -> None:
        self.commits.append((task_id, session_id, output_path))

    def shutdown(self) -> None:
        self.stopped.emit()

    def cancel_current(self) -> None:
        pass


def test_state_output_and_issue_message_identity_rules(tmp_path: Path, workbook_factory) -> None:
    baseline = tmp_path / "项目基线.arxml"
    baseline.write_text("x", encoding="utf-8")
    first = Path(suggest_output_path(str(baseline), "4.84"))
    first.write_text("x", encoding="utf-8")
    second = Path(suggest_output_path(str(baseline), "4.84"))

    assert second.name == "项目基线_v4.84_2.arxml"
    assert validate_output_path(str(baseline), str(baseline)) is not None
    assert controls_for(GuiState.PREVIEW_VALID, inputs_valid=True, cancellable=False).generate_enabled
    assert not controls_for(GuiState.GENERATING, inputs_valid=True, cancellable=True).inputs_enabled

    workbook = read_workbook(workbook_factory()).data
    decision = decisions_to_dto((
        RetentionDecision("/Cfg/Shared", "仍被其他路由使用", "DIRECT_SHARED", (SourceLocation("直接报文路由", 2),)),
    ), workbook)[0]
    assert decision.severity == "DECISION"
    assert [(item.name, item.can_id) for item in decision.messages] == [
        ("SRC_MSG", "0x100"),
        ("DST_MSG", "0x200"),
    ]
    model = IssueTableModel()
    model.set_issues((decision,))
    assert model.headerData(2, Qt.Horizontal) == "报文 ID"
    assert model.headerData(3, Qt.Horizontal) == "报文名称"
    assert model.index(0, 2).data() == "源：0x100 → 目标：0x200"
    assert model.index(0, 3).data() == "源：SRC_MSG → 目标：DST_MSG"

    issue = issues_to_dto((
        ValidationIssue("ROUTE_TEST", "路由问题", location=SourceLocation("直接报文路由", 2)),
    ), workbook)[0]
    assert [(item.role, item.name, item.can_id) for item in issue.messages] == [
        ("SOURCE", "SRC_MSG", "0x100"),
        ("TARGET", "DST_MSG", "0x200"),
    ]

    baseline_warning = issues_to_dto((ValidationIssue(
        "PDUR_ROUTING_GROUP_NON_MAIN_MEMBER",
        "基线一致性警告",
        severity=ValidationSeverity.WARNING,
        file_path=Path("baseline.arxml"),
        location=SourceLocation(),
    ),))[0]
    model.set_issues((baseline_warning,))
    assert model.index(0, 2).data() == "—"
    assert model.index(0, 3).data() == "—"
    assert model.index(0, 5).data() == "baseline.arxml"
    assert model.index(0, 6).data() == (
        "请核对基线 ARXML 中该路由组成员的实际归属；工具不会自动迁移"
    )

    ignored_member = issues_to_dto((ValidationIssue(
        "PDUR_ROUTING_GROUP_NON_CANIF_MEMBERS_IGNORED",
        "非 CanIf 成员已排除",
        severity=ValidationSeverity.WARNING,
        file_path=Path("baseline.arxml"),
        location=SourceLocation(),
    ),))[0]
    model.set_issues((ignored_member,))
    assert model.index(0, 6).data() == (
        "无需修改配置表；工具已排除该成员，如需确认请核对基线 ARXML"
    )

    for code, advice in (
        (
            "PDUR_ROUTING_GROUP_SECONDARY_GROUP_IGNORED",
            "无需修改配置表；专项组保持不变，普通新增使用已确认的应用组",
        ),
        (
            "DIRECT_SOURCE_TYPE_FROM_BASELINE",
            "无需处理；工具采用完整既有源 Rx 的基准类型且不会修改该对象",
        ),
        (
            "SIGNAL_DELETE_NOT_FOUND",
            "无需处理；目标路由已经不存在，本次按幂等语义跳过",
        ),
    ):
        warning = issues_to_dto((ValidationIssue(
            code,
            "无需人工修正的提示",
            severity=ValidationSeverity.WARNING,
            file_path=Path("baseline.arxml"),
            location=SourceLocation(),
        ),))[0]
        model.set_issues((warning,))
        assert model.index(0, 6).data() == advice


def test_feature_cards_are_created_from_dto_without_fixed_ids(qtbot) -> None:
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)
    view_model.features = (
        FeatureSummaryDto(
            "diagnostic_virtual", "虚拟诊断路由", "READY", (MetricDto("count", "数量", 3),),
            details=(ChangeDetailDto("ADD", "诊断", "源端", "目标端", "诊断路由 第 2 行"),),
        ),
    )
    view_model.preview_changed.emit()

    labels = {label.text() for label in window.feature_group.findChildren(QLabel)}
    assert "虚拟诊断路由" in labels
    assert "READY" in labels
    assert "数量：3" in labels
    detail_button = next(
        button for button in window.feature_group.findChildren(QPushButton)
        if button.text() == "查看详情"
    )
    qtbot.mouseClick(detail_button, Qt.LeftButton)
    assert window._detail_dialog is not None
    assert window._detail_dialog.model.rowCount() == 1
    assert window._detail_dialog.model.item(0, 0).text() == "新增"


def test_severity_colour_and_status_banner_state(qtbot) -> None:
    """级别用颜色区分，状态条按流程状态切换配色与文案。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    model = IssueTableModel()
    model.set_issues(issues_to_dto((ValidationIssue(
        "ROUTE_TEST", "路由问题", severity=ValidationSeverity.ERROR,
    ),)))
    assert model.index(0, 0).data(Qt.ForegroundRole) is not None

    view_model.state = GuiState.SUCCESS
    view_model.stage_name = "生成完成"
    view_model.changed.emit()
    assert window.status_banner.rail.property("state") == "success"
    assert window.status_banner.title.text() == "生成完成"


def test_theme_switch_changes_stylesheet_and_remembers_choice(qtbot, tmp_path: Path) -> None:
    """主题切换要立即换肤，并写入设置供下次启动沿用。"""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from UI.styles import DARK, LIGHT

    # 把设置隔离到临时目录，避免测试改动真实的用户设置。
    original_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    try:
        runner = _FakeRunner()
        view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
        window = MainWindow(view_model)
        qtbot.addWidget(window)
        app = QApplication.instance()
        segments = {button.text(): button for button in window.theme_switch.findChildren(QPushButton)}
        qtbot.mouseClick(segments["夜间"], Qt.LeftButton)
        assert window.theme_switch.theme() == "dark"
        assert DARK["canvas"] in app.styleSheet()
        assert window.settings.value("ui/theme") == "dark"

        qtbot.mouseClick(segments["白天"], Qt.LeftButton)
        assert window.theme_switch.theme() == "light"
        assert LIGHT["canvas"] in app.styleSheet()
        assert window.settings.value("ui/theme") == "light"
    finally:
        QSettings.setDefaultFormat(original_format)


def test_cards_are_placed_in_the_two_column_workbench(qtbot) -> None:
    """界面只保留双栏布局：输入卡片在左栏，工作台卡片在右栏。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    assert window._layout_mode == "bento"
    assert window._input_card.parentWidget() is window._left_host
    assert window._actions_card.parentWidget() is window._left_host
    assert window._issues_card.parentWidget() is window._right_host
    assert window.status_banner.parentWidget() is window._right_host


def test_warning_and_decision_rows_can_be_acknowledged(qtbot) -> None:
    """警告与保留决定可人工确认，确认状态回到状态条与筛选计数。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    warning = issues_to_dto((ValidationIssue(
        "PDUR_ROUTING_GROUP_NON_MAIN_MEMBER", "基线一致性警告", severity=ValidationSeverity.WARNING,
    ),))
    decision = decisions_to_dto((RetentionDecision(
        "/Cfg/Shared", "仍被其他路由使用", "DIRECT_SHARED", (SourceLocation("直接报文路由", 2),),
    ),))
    view_model.issues = warning + decision
    view_model.issues_changed.emit(view_model.issues)
    view_model.changed.emit()

    model = window.issue_model
    assert model.rowCount() == 2
    assert model.acknowledgeable(0) and model.acknowledgeable(1)
    assert model.pending_count() == 2

    # 勾选第一行：只影响该行。
    model.setData(model.index(0, model.ACK_COLUMN), Qt.Checked, Qt.CheckStateRole)
    assert model.acknowledged(0) and not model.acknowledged(1)
    assert model.pending_count() == 1

    # 批量确认：把剩余可见行一次确认完。
    window._acknowledge_visible()
    assert model.pending_count() == 0
    assert "待确认" not in window.status_banner.title.text()


def test_output_path_suggestion_is_skipped_without_a_baseline() -> None:
    """没有基准文件时不得抛出异常，界面事件处理不能因此中断。"""
    assert suggest_output_path("") == ""


def test_issue_table_uses_the_custom_delegate_and_folded_columns(qtbot) -> None:
    """问题表用自绘委托呈现，并把报文 ID、报文名称与处理建议并入副行。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    assert isinstance(window.issue_table.itemDelegate(), IssueTableDelegate)
    for column in (2, 3, 6):
        assert window.issue_table.isColumnHidden(column)
    assert not window.issue_table.isColumnHidden(4)


def test_empty_cards_stay_hidden(qtbot) -> None:
    """没有结果时，生成结果卡片与进度条保持隐藏。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    assert not window.result_group.isVisible()
    assert not window.progress.isVisible()
    assert not window.feature_group.isVisible()


def test_generation_is_blocked_until_every_warning_is_acknowledged(qtbot, tmp_path: Path) -> None:
    """人工确认是硬门禁：按钮与快捷键都不能绕过未确认的警告。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    output = tmp_path / "生成结果.arxml"
    view_model.issues = issues_to_dto((ValidationIssue(
        "PDUR_ROUTING_GROUP_NON_MAIN_MEMBER", "基线一致性警告", severity=ValidationSeverity.WARNING,
    ),))
    view_model.issues_changed.emit(view_model.issues)
    view_model.state = GuiState.PREVIEW_VALID
    view_model.session_id = "session-1"
    view_model.output_path = str(output)
    view_model.changed.emit()

    assert view_model.pending_confirmations == 1
    assert not window.generate_button.isEnabled()
    assert "未确认" in window.generate_button.toolTip()

    # 快捷键走的是同一个入口，同样被拦截。
    view_model.start_generate()
    assert runner.commits == []

    # 勾选确认后立刻放行。
    model = window.issue_model
    model.setData(model.index(0, model.ACK_COLUMN), Qt.Checked, Qt.CheckStateRole)
    assert view_model.pending_confirmations == 0
    assert window.generate_button.isEnabled()

    view_model.start_generate()
    assert len(runner.commits) == 1
    assert runner.commits[0][1] == "session-1"


def test_dropping_a_file_on_the_path_input_fills_the_field(qtbot, tmp_path: Path) -> None:
    """拖到文件槽内层输入框也必须生效，而不是只有拖到外框才生效。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    config = tmp_path / "网关配置.xlsx"
    config.write_text("x", encoding="utf-8")
    baseline = tmp_path / "基准.arxml"
    baseline.write_text("x", encoding="utf-8")

    window.config_edit.path_dropped.emit(str(config))
    window.baseline_edit.path_dropped.emit(str(baseline))
    assert view_model.config_path == str(Path(config))
    assert view_model.baseline_path == str(Path(baseline))


def test_severity_filter_pills_show_counts(qtbot) -> None:
    """胶囊分段显示各分类计数，并与问题模型保持一致。"""
    runner = _FakeRunner()
    view_model = GatewayViewModel(runner)  # type: ignore[arg-type]
    window = MainWindow(view_model)
    qtbot.addWidget(window)

    issues = issues_to_dto((
        ValidationIssue("ROUTE_A", "错误", severity=ValidationSeverity.ERROR),
        ValidationIssue("ROUTE_B", "警告", severity=ValidationSeverity.WARNING),
        ValidationIssue("ROUTE_C", "警告二", severity=ValidationSeverity.WARNING),
    ))
    view_model.issues = issues
    view_model.issues_changed.emit(view_model.issues)

    labels = {pill.name.text(): pill.count.text() for pill in window.filter_pills.findChildren(PillButton)}
    assert labels["全部"] == "3"
    assert labels["错误"] == "1"
    assert labels["警告"] == "2"
    assert labels["提示"] == "0"

    window.filter_pills._select("WARNING")
    assert window.issue_proxy._severity == "WARNING"


def test_single_worker_thread_previews_and_commits_prepared_session(
    qtbot, workbook_factory, arxml_factory, tmp_path: Path,
) -> None:
    runner = QtTaskRunner()
    config = workbook_factory()
    baseline = arxml_factory()
    with qtbot.waitSignal(runner.preview_finished, timeout=15_000) as preview_wait:
        runner.start_preview("preview", str(config), str(baseline))
    prepared = preview_wait.args[0]
    assert prepared.status is OperationStatus.SUCCESS
    assert prepared.session_id
    features = {feature.feature_id: feature for feature in prepared.preview.features}
    assert [(detail.action, detail.item_type) for detail in features["direct_message"].details] == [
        ("ADD", "报文"),
    ]
    assert [(detail.action, detail.item_type) for detail in features["signal_route"].details] == [
        ("ADD", "信号"),
    ]
    assert {check.check_id for check in prepared.preview.checks} >= {
        "arxml_schema", "module_canif", "module_com", "module_ecuc", "module_pdur",
    }

    output = tmp_path / "GUI 输出.arxml"
    with qtbot.waitSignal(runner.generation_finished, timeout=15_000) as generation_wait:
        runner.start_commit("commit", prepared.session_id, str(output))
    generated = generation_wait.args[0]
    assert generated.status is OperationStatus.SUCCESS
    assert output.is_file()

    with qtbot.waitSignal(runner.stopped, timeout=5_000):
        runner.shutdown()
