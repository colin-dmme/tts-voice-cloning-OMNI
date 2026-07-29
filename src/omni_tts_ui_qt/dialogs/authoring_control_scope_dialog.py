from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.authoring.catalog import (
    AuthoringFeatureDescriptor,
    AuthoringScopePreset,
)
from omni_tts_core.authoring.schemas import (
    AuthoringControlScope,
    AuthoringFeatureSelection,
)


class AuthoringControlScopeDialog(QDialog):
    """Dynamic editor built entirely from core-supplied feature metadata."""

    def __init__(
        self,
        *,
        descriptors: tuple[AuthoringFeatureDescriptor, ...],
        presets: tuple[AuthoringScopePreset, ...],
        current_scope: AuthoringControlScope,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.descriptors = descriptors
        self.presets = presets
        self.selected_scope = current_scope.model_copy(deep=True)
        self._controls: dict[
            str,
            tuple[QCheckBox, dict[str, QCheckBox]],
        ] = {}
        self._loading = False
        self.setWindowTitle("Phạm vi AI được phép dùng")
        self.setMinimumSize(820, 620)
        self._build()
        self._set_scope(current_scope)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        lead = QLabel(
            "Đây là rào chắn cứng: prompt chỉ thông báo các lựa chọn được phép "
            "và core sẽ loại mọi giá trị AI trả về ngoài phạm vi."
        )
        lead.setWordWrap(True)
        lead.setObjectName("hint")
        outer.addWidget(lead)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Thiết lập nhanh:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Tùy chỉnh", None)
        for preset in self.presets:
            self.preset_combo.addItem(preset.label, preset)
            self.preset_combo.setItemData(
                self.preset_combo.count() - 1,
                preset.tooltip,
                Qt.ItemDataRole.ToolTipRole,
            )
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        preset_row.addWidget(self.preset_combo, 1)
        outer.addLayout(preset_row)

        tabs = QTabWidget()
        for descriptor in self.descriptors:
            tabs.addTab(self._feature_page(descriptor), descriptor.label)
        outer.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Lưu phạm vi"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.accepted.connect(self._accept_scope)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _feature_page(
        self,
        descriptor: AuthoringFeatureDescriptor,
    ) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        description = QLabel(descriptor.description)
        description.setWordWrap(True)
        description.setObjectName("hint")
        page_layout.addWidget(description)

        master = QCheckBox(f"Cho phép AI dùng {descriptor.label.lower()}")
        master.setToolTip(
            "Tắt mục này để AI không được dùng bất kỳ giá trị nào trong nhóm."
        )
        page_layout.addWidget(master)

        action_row = QHBoxLayout()
        select_all = QPushButton("Chọn tất cả")
        clear_all = QPushButton("Bỏ tất cả")
        action_row.addWidget(select_all)
        action_row.addWidget(clear_all)
        action_row.addStretch()
        page_layout.addLayout(action_row)

        content = QWidget()
        grid = QGridLayout(content)
        option_controls: dict[str, QCheckBox] = {}
        columns = 3
        for index, option in enumerate(descriptor.values):
            checkbox = QCheckBox(option.label)
            checkbox.setToolTip(option.tooltip)
            checkbox.stateChanged.connect(self._mark_custom)
            grid.addWidget(checkbox, index // columns, index % columns)
            option_controls[option.value] = checkbox
        grid.setColumnStretch(columns, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)
        self._controls[descriptor.key] = (master, option_controls)

        master.toggled.connect(
            lambda enabled, controls=option_controls: self._set_options_enabled(
                controls,
                enabled,
            )
        )
        master.toggled.connect(self._mark_custom)
        select_all.clicked.connect(
            lambda _checked=False, controls=option_controls: self._check_all(
                controls,
                True,
            )
        )
        clear_all.clicked.connect(
            lambda _checked=False, controls=option_controls: self._check_all(
                controls,
                False,
            )
        )
        return page

    @staticmethod
    def _set_options_enabled(
        controls: dict[str, QCheckBox],
        enabled: bool,
    ) -> None:
        for checkbox in controls.values():
            checkbox.setEnabled(enabled)

    def _check_all(
        self,
        controls: dict[str, QCheckBox],
        checked: bool,
    ) -> None:
        for checkbox in controls.values():
            checkbox.setChecked(checked)
        self._mark_custom()

    def _apply_preset(self, index: int) -> None:
        if self._loading:
            return
        preset = self.preset_combo.itemData(index)
        if isinstance(preset, AuthoringScopePreset):
            self._set_scope(preset.scope, keep_preset_index=True)

    def _set_scope(
        self,
        scope: AuthoringControlScope,
        *,
        keep_preset_index: bool = False,
    ) -> None:
        self._loading = True
        for key, (master, options) in self._controls.items():
            selection = scope.selection(key)
            master.setChecked(selection.enabled)
            selected = set(selection.allowed_values)
            for value, checkbox in options.items():
                checkbox.setChecked(value in selected)
                checkbox.setEnabled(selection.enabled)
        if not keep_preset_index:
            self.preset_combo.setCurrentIndex(0)
        self._loading = False

    def _mark_custom(self, *_args) -> None:
        if self._loading:
            return
        self._loading = True
        self.preset_combo.setCurrentIndex(0)
        self._loading = False

    def _accept_scope(self) -> None:
        self.selected_scope = AuthoringControlScope(
            features={
                key: AuthoringFeatureSelection(
                    enabled=master.isChecked(),
                    allowed_values=[
                        value
                        for value, checkbox in options.items()
                        if checkbox.isChecked()
                    ],
                )
                for key, (master, options) in self._controls.items()
            }
        )
        self.accept()
