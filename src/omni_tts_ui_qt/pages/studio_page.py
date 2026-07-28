"""Studio page: voice sidebar + text/queue tabs + settings panel.

The single-window studio inspired by QH Voice Studio. Composition only — queue
behaviour lives in QueueController, generation settings in SettingsPanel, and
request building in the core AppController.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.file_queue import STATUS_LABELS, FileQueueStatus
from omni_tts_core.generation_history import (
    GenerationHistoryStore,
    HistoryStatus,
)
from omni_tts_core.path_intake import parse_path_text
from omni_tts_core.text.source_reader import SUPPORTED_TEXT_EXTENSIONS
from omni_tts_core.ui_presenters import labels
from omni_tts_core.ui_presenters.search import matches_search
from omni_tts_ui_qt.background import GenerationWorker
from omni_tts_ui_qt.context import AppContext
from omni_tts_ui_qt.models.queue_model import ProgressBarDelegate, QueueTableModel
from omni_tts_ui_qt.models.history_model import HistoryTableModel
from omni_tts_ui_qt.pages.queue_controller import QueueController
from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
from omni_tts_ui_qt.widgets.higgs_script_toolbar import HiggsScriptToolbar
from omni_tts_ui_qt.widgets.common import open_path

_FILTERS = [
    ("Tất cả", "all"),
    ("Chờ chạy", FileQueueStatus.PENDING.value),
    ("Đang chạy", FileQueueStatus.RUNNING.value),
    ("Thành công", FileQueueStatus.DONE.value),
    ("Lỗi", FileQueueStatus.FAILED.value),
    ("Đã hủy", FileQueueStatus.CANCELLED.value),
    ("Gián đoạn", FileQueueStatus.INTERRUPTED.value),
    ("Cần chạy lại", FileQueueStatus.OUTDATED.value),
]


class _DropTableView(QTableView):
    paths_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths: list[Path] = []
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.toLocalFile()]
        elif event.mimeData().hasText():
            paths = parse_path_text(event.mimeData().text())
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()


class StudioPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._text_worker: GenerationWorker | None = None
        self._last_text_result = None
        self._active_text_settings = None
        self._active_text_char_count = 0
        self._active_text_source_label = ""
        self._current_model_id = ""
        self._queue_status_message = ""
        self._queue_active = False
        self._text_active = False

        self.history_store = GenerationHistoryStore()
        self.queue = QueueController(context, self.history_store)
        self.settings_panel = SettingsPanel(context)
        context.register_settings_provider(self.settings_panel.current_settings)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self.settings_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 640, 380])
        self._splitter = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._wire()
        self._load_preferences()
        self._refresh_sidebar()
        self._sync_higgs_script_toolbar()
        self._refresh_queue()

    # --- Sidebar ------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        title = QLabel("GIỌNG ĐỌC")
        title.setObjectName("sidebarTitle")
        self.voice_search = QLineEdit()
        self.voice_search.setPlaceholderText("Tìm giọng…")
        self.voice_list = QListWidget()
        self.voice_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.voice_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.voice_preview_button = QPushButton("▶ Nghe giọng mẫu")
        self.voice_preview_button.setEnabled(False)
        self.voice_preview_button.setToolTip(
            "Mở audio mẫu của profile giọng bằng trình nghe nhạc mặc định. "
            "Giọng cố định của model không có file mẫu sẵn nên không nghe thử được."
        )
        layout.addWidget(title)
        layout.addWidget(self.voice_search)
        layout.addWidget(self.voice_list, 1)
        layout.addWidget(self.voice_preview_button)
        self.voice_search.textChanged.connect(self._filter_voices)
        self.voice_list.itemClicked.connect(self._on_voice_selected)
        self.voice_list.currentItemChanged.connect(self._update_voice_preview_button)
        self.voice_list.itemDoubleClicked.connect(self._preview_voice_item)
        self.voice_list.customContextMenuRequested.connect(self._voice_context_menu)
        self.voice_preview_button.clicked.connect(self._preview_current_voice)
        panel.setMinimumWidth(210)
        return panel

    def _refresh_sidebar(self) -> None:
        model_id = self.settings_panel.current_model_id()
        self._current_model_id = model_id
        self.voice_list.clear()
        try:
            presets = self.ctrl.voice_preset_choices(model_id, include_none=False)
        except Exception:
            presets = []
        for label, voice_id in presets:
            item = QListWidgetItem(f"🎧  {label}")
            item.setData(Qt.ItemDataRole.UserRole, ("fixed", voice_id))
            self.voice_list.addItem(item)
        settings = self.settings_panel.current_settings()
        for label, voice_id in self.ctrl.higgs_custom_voice_choices(settings):
            item = QListWidgetItem(f"🎧  {label}")
            item.setData(Qt.ItemDataRole.UserRole, ("fixed", voice_id))
            self.voice_list.addItem(item)
        for name, profile_id in self.ctrl.voice_profile_choices():
            item = QListWidgetItem(f"🗣  {name}  ·  Profile")
            item.setData(Qt.ItemDataRole.UserRole, ("profile", profile_id))
            self.voice_list.addItem(item)
        if self.voice_list.count() == 0:
            placeholder = QListWidgetItem("Model này dùng giọng mặc định.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.voice_list.addItem(placeholder)
        self._filter_voices(self.voice_search.text())
        self._update_voice_preview_button()

    def _filter_voices(self, text: str) -> None:
        needle = text
        for row in range(self.voice_list.count()):
            item = self.voice_list.item(row)
            item.setHidden(not matches_search(item.text(), needle))

    def _on_voice_selected(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        mode, value = data
        if mode == "fixed":
            self.settings_panel.set_fixed_voice(value)
        else:
            self.settings_panel.set_profile(value)

    def _voice_item_profile_id(self, item: QListWidgetItem | None) -> str | None:
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not data:
            return None
        mode, value = data
        return value if mode == "profile" else None

    def _update_voice_preview_button(self, *_args) -> None:
        enabled = self._voice_item_profile_id(self.voice_list.currentItem()) is not None
        self.voice_preview_button.setEnabled(enabled)

    def _preview_current_voice(self) -> None:
        self._preview_voice_item(self.voice_list.currentItem())

    def _preview_voice_item(self, item: QListWidgetItem | None) -> None:
        profile_id = self._voice_item_profile_id(item)
        if profile_id is None:
            return
        self._play_audio(lambda: self.ctrl.play_voice_profile_sample(profile_id))

    def _voice_context_menu(self, position) -> None:
        item = self.voice_list.itemAt(position)
        profile_id = self._voice_item_profile_id(item)
        if profile_id is None:
            return
        menu = QMenu(self)
        menu.addAction("▶ Nghe giọng mẫu", lambda: self._preview_voice_item(item))
        menu.addAction("Mở thư mục audio mẫu", lambda: self._open_profile_folder(profile_id))
        menu.exec(self.voice_list.viewport().mapToGlobal(position))

    def _open_profile_folder(self, profile_id: str) -> None:
        try:
            profile = self.ctrl.voice_profile(profile_id)
        except Exception as error:
            QMessageBox.warning(self, "Không mở được thư mục", str(error))
            return
        open_path(Path(profile.audio_path).parent)

    # --- Center -------------------------------------------------------------

    def _build_center(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 4)

        toolbar = QHBoxLayout()
        add_file = QPushButton("+ Thêm file")
        add_folder = QPushButton("+ Thêm thư mục")
        paste_path = QPushButton("Dán đường dẫn")
        paste_text = QPushButton("Dán văn bản")
        add_file.clicked.connect(self._add_files)
        add_folder.clicked.connect(self._add_folder)
        paste_path.clicked.connect(self._paste_paths)
        paste_text.clicked.connect(self._paste_text_job)
        for button in (add_file, add_folder, paste_path, paste_text):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_text_tab(), "Văn bản")
        self.tabs.addTab(self._build_queue_tab(), "Hàng đợi file")
        self.tabs.addTab(self._build_history_tab(), "Lịch sử")
        layout.addWidget(self.tabs, 1)
        return panel

    def _build_text_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("Nhập nội dung cần đọc…")
        self.higgs_script_toolbar = HiggsScriptToolbar()
        self.higgs_script_toolbar.setVisible(False)
        self.higgs_script_toolbar.token_requested.connect(
            self._insert_higgs_token
        )
        self.higgs_script_toolbar.validate_requested.connect(
            self._validate_higgs_script
        )
        self.higgs_script_toolbar.preview_requested.connect(
            self._preview_higgs_requests
        )
        stem_row = QHBoxLayout()
        self.output_stem = QLineEdit()
        self.output_stem.setPlaceholderText("Tên file xuất (tùy chọn)")
        stem_row.addWidget(QLabel("Tên file:"))
        stem_row.addWidget(self.output_stem, 1)
        self.generate_button = QPushButton("Tạo giọng đọc")
        self.generate_button.setObjectName("primaryButton")
        self.text_cancel_button = QPushButton("Hủy")
        self.text_cancel_button.setEnabled(False)
        stem_row.addWidget(self.generate_button)
        stem_row.addWidget(self.text_cancel_button)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setMaximumHeight(140)
        result_header = QHBoxLayout()
        result_header.addWidget(QLabel("Kết quả:"))
        result_header.addStretch()
        self.text_preview_button = QPushButton("▶ Nghe thử")
        self.text_preview_button.setEnabled(False)
        self.text_preview_button.setToolTip(
            "Mở file audio kết quả bằng trình nghe nhạc mặc định của Windows."
        )
        result_header.addWidget(self.text_preview_button)
        text_progress_row = QHBoxLayout()
        self.text_job_label = QLabel("Sẵn sàng")
        self.text_job_label.setObjectName("hint")
        self.text_progress_bar = QProgressBar()
        self.text_progress_bar.setVisible(False)
        text_progress_row.addWidget(self.text_job_label, 1)
        text_progress_row.addWidget(self.text_progress_bar, 1)
        layout.addWidget(self.higgs_script_toolbar)
        layout.addWidget(self.text_input, 1)
        layout.addLayout(stem_row)
        layout.addLayout(text_progress_row)
        layout.addLayout(result_header)
        layout.addWidget(self.result_view)
        self.generate_button.clicked.connect(self._generate_text)
        self.text_cancel_button.clicked.connect(self._cancel_text)
        self.text_preview_button.clicked.connect(self._preview_text_audio)
        return widget

    def _build_queue_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        filter_row = QHBoxLayout()
        self.filter_combo = QComboBox()
        for label, value in _FILTERS:
            self.filter_combo.addItem(label, value)
        self.queue_search = QLineEdit()
        self.queue_search.setPlaceholderText("Tìm theo tên file…")
        self.queue_preview_button = self._compact_button(
            "▶", "Phát audio kết quả bằng trình nghe nhạc mặc định."
        )
        self.queue_preview_button.setEnabled(False)
        self.queue_copy_audio_button = self._compact_button(
            "⧉ Audio", "Copy đường dẫn file audio kết quả."
        )
        self.queue_copy_srt_button = self._compact_button(
            "⧉ SRT", "Copy đường dẫn file phụ đề SRT kết quả."
        )
        self.queue_copy_audio_button.setEnabled(False)
        self.queue_copy_srt_button.setEnabled(False)
        self.delete_button = QPushButton("Xóa mục chọn")
        self.reset_button = QPushButton("Đặt lại")
        self.clear_button = QPushButton("Xóa tất cả")
        filter_row.addWidget(QLabel("Lọc:"))
        filter_row.addWidget(self.filter_combo)
        filter_row.addWidget(self.queue_search, 1)
        filter_row.addWidget(self.queue_preview_button)
        filter_row.addWidget(self.queue_copy_audio_button)
        filter_row.addWidget(self.queue_copy_srt_button)
        filter_row.addWidget(self.delete_button)
        filter_row.addWidget(self.reset_button)
        filter_row.addWidget(self.clear_button)
        layout.addLayout(filter_row)

        self.queue_model = QueueTableModel()
        self.queue_table = _DropTableView()
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_table.setItemDelegateForColumn(3, ProgressBarDelegate(self.queue_table))
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.queue_table, 1)
        self.queue_summary = QLabel("")
        self.queue_summary.setObjectName("hint")
        layout.addWidget(self.queue_summary)
        action_bar = QHBoxLayout()
        self.queue_job_label = QLabel("Sẵn sàng")
        self.queue_job_label.setObjectName("hint")
        self.queue_progress_bar = QProgressBar()
        self.queue_progress_bar.setVisible(False)
        self.run_button = QPushButton("Chạy hàng đợi")
        self.run_button.setObjectName("primaryButton")
        self.run_selected_button = QPushButton("Chạy mục chọn")
        self.retry_button = QPushButton("Chạy lại lỗi")
        self.cancel_button = QPushButton("Hủy")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.run_button.clicked.connect(lambda: self._run_queue("pending"))
        self.run_selected_button.clicked.connect(lambda: self._run_queue("selected"))
        self.retry_button.clicked.connect(lambda: self._run_queue("failed"))
        self.cancel_button.clicked.connect(self._cancel)
        action_bar.addWidget(self.queue_job_label, 1)
        action_bar.addWidget(self.queue_progress_bar, 1)
        for button in (
            self.run_button,
            self.run_selected_button,
            self.retry_button,
            self.cancel_button,
        ):
            action_bar.addWidget(button)
        layout.addLayout(action_bar)

        self.filter_combo.currentIndexChanged.connect(self._refresh_queue)
        self.queue_search.textChanged.connect(self._refresh_queue)
        self.delete_button.clicked.connect(self._delete_selected)
        self.reset_button.clicked.connect(self._reset_selected)
        self.clear_button.clicked.connect(self._clear_queue)
        self.queue_preview_button.clicked.connect(self._preview_selected_queue_audio)
        self.queue_copy_audio_button.clicked.connect(
            lambda: self._copy_selected_queue_path("merged_audio")
        )
        self.queue_copy_srt_button.clicked.connect(
            lambda: self._copy_selected_queue_path("srt")
        )
        self.queue_table.paths_dropped.connect(self.queue.add_paths)
        self.queue_table.customContextMenuRequested.connect(self._queue_context_menu)
        self.queue_table.doubleClicked.connect(self._preview_queue_index)
        self.queue_table.selectionModel().selectionChanged.connect(
            self._update_queue_output_buttons
        )
        return widget

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        toolbar = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Tìm theo nguồn hoặc model…")
        self.history_preview_button = self._compact_button(
            "▶", "Phát lại audio của lịch sử đang chọn."
        )
        self.history_copy_audio_button = self._compact_button(
            "⧉ Audio", "Copy đường dẫn audio của lịch sử đang chọn."
        )
        self.history_copy_srt_button = self._compact_button(
            "⧉ SRT", "Copy đường dẫn SRT của lịch sử đang chọn."
        )
        self.history_delete_button = QPushButton("Xóa mục chọn")
        self.history_clear_button = QPushButton("Xóa lịch sử")
        for button in (
            self.history_preview_button,
            self.history_copy_audio_button,
            self.history_copy_srt_button,
        ):
            button.setEnabled(False)
        toolbar.addWidget(self.history_search, 1)
        toolbar.addWidget(self.history_preview_button)
        toolbar.addWidget(self.history_copy_audio_button)
        toolbar.addWidget(self.history_copy_srt_button)
        toolbar.addWidget(self.history_delete_button)
        toolbar.addWidget(self.history_clear_button)
        layout.addLayout(toolbar)

        self.history_model = HistoryTableModel()
        self.history_table = QTableView()
        self.history_table.setModel(self.history_model)
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.history_table, 1)
        self.history_summary = QLabel("")
        self.history_summary.setObjectName("hint")
        layout.addWidget(self.history_summary)

        self.history_search.textChanged.connect(self._refresh_history)
        self.history_preview_button.clicked.connect(self._preview_history_audio)
        self.history_copy_audio_button.clicked.connect(
            lambda: self._copy_selected_history_path("audio")
        )
        self.history_copy_srt_button.clicked.connect(
            lambda: self._copy_selected_history_path("srt")
        )
        self.history_delete_button.clicked.connect(self._delete_history_selected)
        self.history_clear_button.clicked.connect(self._clear_history)
        self.history_table.doubleClicked.connect(
            lambda _index: self._preview_history_audio()
        )
        self.history_table.selectionModel().selectionChanged.connect(
            self._update_history_output_buttons
        )
        self._refresh_history()
        return widget

    @staticmethod
    def _compact_button(text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setMaximumWidth(76 if len(text) > 1 else 36)
        button.setMinimumWidth(32)
        return button

    # --- Wiring -------------------------------------------------------------

    def _wire(self) -> None:
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        self.queue.items_changed.connect(self._refresh_queue)
        self.queue.log.connect(self.context.log)
        self.queue.worker_status.connect(self._on_queue_worker_status)
        self.queue.progress.connect(self._on_queue_progress)
        self.queue.run_state_changed.connect(self._on_run_state)
        self.queue.history_changed.connect(self._refresh_history)
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(400)
        self._settings_timer.timeout.connect(self._apply_settings_change)

    def _on_settings_changed(self) -> None:
        self._settings_timer.start()

    def _apply_settings_change(self) -> None:
        if self.settings_panel.current_model_id() != self._current_model_id:
            self._refresh_sidebar()
        self._sync_higgs_script_toolbar()
        if not self.queue.is_running():
            self.queue.mark_settings_outdated(self.settings_panel.current_settings())
        # Persist after the same short debounce used for queue invalidation, so
        # changing a spin box survives an app crash/restart instead of waiting
        # until the main window closes normally.
        data = self.context.preferences.load()
        self.save_preferences(data)
        self.context.preferences.save(data)

    def _sync_higgs_script_toolbar(self) -> None:
        policy = self.ctrl.control_policy(
            self.settings_panel.current_model_id()
        )
        self.higgs_script_toolbar.setVisible(bool(policy.higgs_script))

    def _insert_higgs_token(self, token: str) -> None:
        cursor = self.text_input.textCursor()
        cursor.insertText(token)
        self.text_input.setTextCursor(cursor)
        self.text_input.setFocus()

    def _validate_higgs_script(self) -> None:
        analysis = self.ctrl.analyze_higgs_script(
            self.text_input.toPlainText()
        )
        detail = analysis.summary
        if analysis.issues:
            detail += "\n\n" + "\n".join(
                f"- Vị trí {issue.offset + 1}: {issue.message}"
                for issue in analysis.issues[:12]
            )
            if len(analysis.issues) > 12:
                detail += f"\n- … và {len(analysis.issues) - 12} vấn đề khác."
        QMessageBox.information(self, "Kiểm tra Higgs Script", detail)

    def _preview_higgs_requests(self) -> None:
        try:
            chunks = self.ctrl.preview_higgs_script(
                self.text_input.toPlainText(),
                self.settings_panel.current_settings(),
            )
        except Exception as error:
            QMessageBox.warning(self, "Không xem trước được", str(error))
            return
        if not chunks:
            QMessageBox.information(
                self, "Higgs request", "Chưa có nội dung để biên dịch."
            )
            return
        preview = "\n\n".join(
            f"REQUEST {index}/{len(chunks)}\n{chunk}"
            for index, chunk in enumerate(chunks[:20], start=1)
        )
        if len(chunks) > 20:
            preview += f"\n\n… còn {len(chunks) - 20} request."
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Higgs request sau khi chia")
        dialog.setText(
            f"Đã biên dịch thành {len(chunks)} request. "
            "Mở “Show Details” để kiểm tra delivery state và ranh giới chunk."
        )
        dialog.setDetailedText(preview)
        dialog.exec()

    # --- Queue tab actions --------------------------------------------------

    def _add_files(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_TEXT_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn file nguồn", "", f"Văn bản ({patterns})")
        if files:
            self.queue.add_paths([Path(f) for f in files])
            self.tabs.setCurrentIndex(1)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục nguồn")
        if folder:
            self.queue.add_paths([Path(folder)])
            self.tabs.setCurrentIndex(1)

    def _paste_paths(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Dán đường dẫn", "Mỗi dòng một đường dẫn:")
        if ok and text.strip():
            self.queue.add_from_text(text)
            self.tabs.setCurrentIndex(1)

    def _paste_text_job(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.text_input.setFocus()

    def _selected_item_ids(self) -> list[str]:
        ids: list[str] = []
        for index in self.queue_table.selectionModel().selectedRows():
            item = self.queue_model.item_at(index.row())
            if item:
                ids.append(item.item_id)
        return ids

    def _selected_queue_item(self):
        rows = self.queue_table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self.queue_model.item_at(rows[0].row())

    def _update_queue_output_buttons(self, *_args) -> None:
        item = self._selected_queue_item()
        done = bool(item and item.status == FileQueueStatus.DONE)
        audio_path = (
            item.output_manifest.preferred_audio_path()
            if done and item is not None
            else None
        )
        playable_audio = (
            item.output_manifest.preferred_audio_path(existing_only=True)
            if done and item is not None
            else None
        )
        srt = (
            item.output_manifest.preferred_srt_path()
            if done and item is not None
            else None
        )
        self.queue_preview_button.setEnabled(playable_audio is not None)
        self.queue_copy_audio_button.setEnabled(audio_path is not None)
        self.queue_copy_srt_button.setEnabled(srt is not None)

    def _delete_selected(self) -> None:
        self.queue.delete(self._selected_item_ids())

    def _reset_selected(self) -> None:
        self.queue.reset(self._selected_item_ids())

    def _clear_queue(self) -> None:
        if QMessageBox.question(self, "Xóa tất cả", "Xóa toàn bộ hàng đợi?") == QMessageBox.StandardButton.Yes:
            self.queue.clear()

    def _refresh_queue(self) -> None:
        status_filter = self.filter_combo.currentData() if hasattr(self, "filter_combo") else "all"
        needle = self.queue_search.text() if hasattr(self, "queue_search") else ""
        items = []
        counts: dict = {}
        for item in self.queue.items():
            counts[item.status] = counts.get(item.status, 0) + 1
            if status_filter and status_filter != "all" and item.status.value != status_filter:
                continue
            if not matches_search(item.source_path.name, needle):
                continue
            items.append(item)
        self.queue_model.set_items(items)
        self._update_queue_output_buttons()
        total = sum(counts.values())
        done = counts.get(FileQueueStatus.DONE, 0)
        failed = counts.get(FileQueueStatus.FAILED, 0)
        self.queue_summary.setText(
            f"Hiển thị {len(items)}/{total} · Thành công {done} · Lỗi {failed}"
        )

    def _queue_context_menu(self, position) -> None:
        index = self.queue_table.indexAt(position)
        item = self.queue_model.item_at(index.row()) if index.isValid() else None
        if item is None:
            return
        if not self.queue_table.selectionModel().isRowSelected(
            index.row(), index.parent()
        ):
            self.queue_table.selectRow(index.row())
        menu = QMenu(self)
        menu.addAction(
            "Mở file nguồn để sửa",
            lambda: self._open_queue_path(
                lambda: self.ctrl.open_source_file(item.source_path),
                "Đã mở file nguồn",
            ),
        )
        menu.addAction(
            "Mở thư mục file nguồn",
            lambda: self._open_queue_path(
                lambda: self.ctrl.open_source_folder(item.source_path),
                "Đã mở thư mục file nguồn",
            ),
        )
        menu.addSeparator()
        if item.status == FileQueueStatus.DONE:
            menu.addAction("▶ Phát audio", lambda: self._preview_queue_audio(item))
            menu.addAction(
                "Mở thư mục kết quả",
                lambda: self._open_queue_path(
                    lambda: self.ctrl.open_result_folder(item.output_manifest),
                    "Đã mở thư mục kết quả",
                ),
            )
            menu.addAction(
                "Copy đường dẫn audio",
                lambda: self._copy_manifest_path(item.output_manifest, "audio"),
            )
            menu.addAction(
                "Copy đường dẫn SRT",
                lambda: self._copy_manifest_path(item.output_manifest, "srt"),
            )
            menu.addSeparator()
        menu.addAction("Chạy lại", lambda: self._run_selected_context())
        menu.addAction("Đặt lại trạng thái", self._reset_selected)
        menu.addAction("Xóa", self._delete_selected)
        menu.exec(self.queue_table.viewport().mapToGlobal(position))

    def _run_selected_context(self) -> None:
        self._run_queue("selected")

    def _preview_selected_queue_audio(self) -> None:
        item = self._selected_queue_item()
        if item is not None:
            self._preview_queue_audio(item)

    def _preview_queue_index(self, index) -> None:
        item = self.queue_model.item_at(index.row()) if index.isValid() else None
        if item and item.status == FileQueueStatus.DONE:
            self._preview_queue_audio(item)

    def _preview_queue_audio(self, item) -> None:
        self._play_audio(lambda: self.ctrl.play_queue_audio(item.output_manifest))

    def _open_queue_path(self, action, success_message: str) -> None:
        try:
            path = action()
        except Exception as error:
            QMessageBox.warning(self, "Không mở được đường dẫn", str(error))
            return
        self.context.log(f"{success_message}: {path}")

    def _copy_selected_queue_path(self, kind: str) -> None:
        item = self._selected_queue_item()
        if item is not None:
            self._copy_manifest_path(item.output_manifest, kind)

    def _copy_manifest_path(self, manifest, kind: str) -> None:
        path = (
            manifest.preferred_audio_path()
            if kind == "audio" or kind == "merged_audio"
            else manifest.preferred_srt_path()
        )
        if path is None:
            QMessageBox.information(
                self, "Chưa có kết quả", f"Không có đường dẫn {kind.upper()} để copy."
            )
            return
        QApplication.clipboard().setText(str(path))
        self.context.log(f"Đã copy đường dẫn: {path}")

    # --- History tab actions ------------------------------------------------

    def _refresh_history(self, *_args) -> None:
        needle = self.history_search.text() if hasattr(self, "history_search") else ""
        entries = self.history_store.list_entries()
        visible = [
            entry
            for entry in entries
            if matches_search(
                " ".join(
                    (
                        entry.source_label,
                        str(entry.source_path or ""),
                        entry.model_id,
                        entry.provider_id,
                    )
                ),
                needle,
            )
        ]
        self.history_model.set_items(visible)
        self.history_summary.setText(
            f"Hiển thị {len(visible)}/{len(entries)} lần xử lý gần nhất"
        )
        self._update_history_output_buttons()

    def _selected_history_entries(self):
        rows = self.history_table.selectionModel().selectedRows()
        return [
            item
            for index in rows
            if (item := self.history_model.item_at(index.row())) is not None
        ]

    def _selected_history_entry(self):
        entries = self._selected_history_entries()
        return entries[0] if len(entries) == 1 else None

    def _update_history_output_buttons(self, *_args) -> None:
        entry = self._selected_history_entry()
        audio_path = (
            entry.output_manifest.preferred_audio_path()
            if entry is not None
            else None
        )
        playable_audio = (
            entry.output_manifest.preferred_audio_path(existing_only=True)
            if entry is not None
            else None
        )
        srt = (
            entry.output_manifest.preferred_srt_path()
            if entry is not None
            else None
        )
        self.history_preview_button.setEnabled(playable_audio is not None)
        self.history_copy_audio_button.setEnabled(audio_path is not None)
        self.history_copy_srt_button.setEnabled(srt is not None)

    def _preview_history_audio(self) -> None:
        entry = self._selected_history_entry()
        if entry is not None:
            self._play_audio(
                lambda: self.ctrl.play_queue_audio(entry.output_manifest)
            )

    def _copy_selected_history_path(self, kind: str) -> None:
        entry = self._selected_history_entry()
        if entry is not None:
            self._copy_manifest_path(entry.output_manifest, kind)

    def _delete_history_selected(self) -> None:
        entries = self._selected_history_entries()
        if not entries:
            return
        self.history_store.delete([entry.history_id for entry in entries])
        self._refresh_history()

    def _clear_history(self) -> None:
        if (
            QMessageBox.question(
                self, "Xóa lịch sử", "Xóa toàn bộ lịch sử xử lý?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        removed = self.history_store.clear()
        self.context.log(f"Đã xóa {removed} mục lịch sử.")
        self._refresh_history()

    # --- Running ------------------------------------------------------------

    def _run_queue(self, scope: str) -> None:
        settings = self.settings_panel.current_settings()
        self.queue.run(scope, settings, self._selected_item_ids())

    def _cancel(self) -> None:
        self.queue.cancel()

    def _on_queue_progress(self, percent: float, message: str) -> None:
        if percent < 0:
            self.queue_progress_bar.setVisible(False)
            self.queue_job_label.setText("Sẵn sàng")
            return
        self.queue_progress_bar.setVisible(True)
        self.queue_progress_bar.setValue(
            int(max(0.0, min(1.0, percent)) * 100)
        )
        self.queue_job_label.setText(message)

    def _on_run_state(self, running: bool) -> None:
        self._queue_active = running
        self.cancel_button.setEnabled(running)
        for button in (self.run_button, self.run_selected_button, self.retry_button):
            button.setEnabled(not running)
        self._sync_global_worker_status()

    def _on_queue_worker_status(self, status: str, message: str) -> None:
        self._queue_status_message = message
        self._sync_global_worker_status(status, message)

    def _sync_global_worker_status(
        self, fallback_status: str = "ready", fallback_message: str = "Sẵn sàng"
    ) -> None:
        queue_running = self._queue_active
        text_running = self._text_active
        if queue_running and text_running:
            self.context.set_worker_status(
                "processing", "Đang chạy độc lập: Văn bản + Hàng đợi"
            )
        elif queue_running:
            self.context.set_worker_status(
                "processing", self._queue_status_message or "Đang chạy hàng đợi…"
            )
        elif text_running:
            self.context.set_worker_status("processing", "Đang tạo giọng đọc…")
        else:
            self.context.set_worker_status(fallback_status, fallback_message)

    # --- Text generation ----------------------------------------------------

    def _generate_text(self) -> None:
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Thiếu nội dung", "Bạn chưa nhập nội dung cần đọc.")
            return
        settings = self.settings_panel.current_settings()
        stem = self.output_stem.text().strip()
        if stem:
            settings.output_stem = stem
        self._active_text_settings = settings
        self._active_text_char_count = len(text)
        self._active_text_source_label = stem or "Văn bản trực tiếp"
        self._last_text_result = None
        self.text_preview_button.setEnabled(False)
        self._text_worker = GenerationWorker(self.ctrl, "text", settings, text=text)
        self._text_worker.progress_event.connect(self._on_text_progress)
        self._text_worker.completed.connect(self._on_text_done)
        self._text_worker.failed.connect(self._on_text_failed)
        self._text_worker.cancelled.connect(self._on_text_cancelled)
        self.generate_button.setEnabled(False)
        self.text_cancel_button.setEnabled(True)
        self._text_active = True
        self.text_progress_bar.setVisible(True)
        self.text_progress_bar.setValue(0)
        self.text_job_label.setText("Đang tạo giọng đọc…")
        self._sync_global_worker_status()
        self.result_view.setPlainText("Đang xử lý…")
        self._text_worker.start()

    def _cancel_text(self) -> None:
        if self._text_worker is not None:
            self._text_worker.request_cancel()

    def _on_text_progress(self, event) -> None:
        percent = (event.current / event.total) if event.total else 0.0
        self.text_progress_bar.setValue(
            int(max(0.0, min(1.0, percent)) * 100)
        )
        self.text_job_label.setText(event.message)
        self.context.log(event.message)

    def _on_text_done(self, result) -> None:
        self._last_text_result = result
        self.text_preview_button.setEnabled(True)
        self.result_view.setPlainText(labels.format_result(result))
        self._record_text_history(HistoryStatus.DONE, result=result)
        self._finish_text("ready", "Đã tạo giọng đọc.")

    def _on_text_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"Lỗi: {message}")
        self._record_text_history(HistoryStatus.FAILED, error=message)
        self._finish_text("error", "Tạo giọng thất bại.")
        if "license" in message.lower() or "License" in message:
            self.context.show_page("license")

    def _on_text_cancelled(self) -> None:
        self.result_view.setPlainText("Đã hủy.")
        self._record_text_history(
            HistoryStatus.CANCELLED, error="Đã hủy khi đang xử lý"
        )
        self._finish_text("paused", "Đã hủy tạo giọng.")

    def _preview_text_audio(self) -> None:
        if self._last_text_result is not None:
            self._play_audio(
                lambda: self.ctrl.play_result_audio(self._last_text_result)
            )

    def _play_audio(self, action) -> None:
        try:
            path = action()
        except Exception as error:
            QMessageBox.warning(self, "Không phát được audio", str(error))
            return
        self.context.log(f"Đã mở audio bằng ứng dụng mặc định: {path}")

    def _finish_text(self, status: str, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.text_cancel_button.setEnabled(False)
        self.text_progress_bar.setVisible(False)
        self.text_job_label.setText("Sẵn sàng")
        self.context.log(message)
        self._text_worker = None
        self._active_text_settings = None
        self._text_active = False
        self._sync_global_worker_status(status, message)

    def _record_text_history(
        self, status: HistoryStatus, *, result=None, error: str = ""
    ) -> None:
        settings = self._active_text_settings
        if settings is None:
            return
        self.history_store.record(
            mode="text",
            source_label=self._active_text_source_label,
            char_count=self._active_text_char_count,
            model_id=settings.model_id,
            provider_id=self.ctrl.provider_of_model(settings.model_id),
            status=status,
            result=result,
            error=error,
        )
        self._refresh_history()

    # --- Preferences / lifecycle -------------------------------------------

    def _load_preferences(self) -> None:
        data = self.context.preferences.load()
        self.settings_panel.load_preferences(data)
        splitter_state = data.get("main_splitter_b64") or ""
        if splitter_state:
            from PySide6.QtCore import QByteArray

            self._splitter.restoreState(QByteArray.fromBase64(splitter_state.encode("ascii")))
        status = data.get("queue_status_filter", "all")
        index = self.filter_combo.findData(status)
        if index >= 0:
            self.filter_combo.setCurrentIndex(index)

    def save_preferences(self, data: dict) -> None:
        self.settings_panel.save_preferences(data)
        data["main_splitter_b64"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        data["queue_status_filter"] = self.filter_combo.currentData()

    def is_busy(self) -> bool:
        return self.queue.is_running() or (self._text_worker is not None and self._text_worker.isRunning())
