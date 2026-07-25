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
from omni_tts_core.path_intake import parse_path_text
from omni_tts_core.text.source_reader import SUPPORTED_TEXT_EXTENSIONS
from omni_tts_core.ui_presenters import labels
from omni_tts_core.ui_presenters.search import matches_search
from omni_tts_ui_qt.background import GenerationWorker
from omni_tts_ui_qt.context import AppContext
from omni_tts_ui_qt.models.queue_model import ProgressBarDelegate, QueueTableModel
from omni_tts_ui_qt.pages.queue_controller import QueueController
from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
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
        self._current_model_id = ""

        self.queue = QueueController(context)
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
        layout.addWidget(title)
        layout.addWidget(self.voice_search)
        layout.addWidget(self.voice_list, 1)
        self.voice_search.textChanged.connect(self._filter_voices)
        self.voice_list.itemClicked.connect(self._on_voice_selected)
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
        for name, profile_id in self.ctrl.voice_profile_choices():
            item = QListWidgetItem(f"🗣  {name}  ·  Profile")
            item.setData(Qt.ItemDataRole.UserRole, ("profile", profile_id))
            self.voice_list.addItem(item)
        if self.voice_list.count() == 0:
            placeholder = QListWidgetItem("Model này dùng giọng mặc định.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.voice_list.addItem(placeholder)
        self._filter_voices(self.voice_search.text())

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
        layout.addWidget(self.tabs, 1)

        action_bar = QHBoxLayout()
        self.job_label = QLabel("Sẵn sàng")
        self.job_label.setObjectName("hint")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
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
        action_bar.addWidget(self.job_label, 1)
        action_bar.addWidget(self.progress_bar, 1)
        for button in (self.run_button, self.run_selected_button, self.retry_button, self.cancel_button):
            action_bar.addWidget(button)
        layout.addLayout(action_bar)
        return panel

    def _build_text_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("Nhập nội dung cần đọc…")
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
        layout.addWidget(self.text_input, 1)
        layout.addLayout(stem_row)
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
        self.queue_preview_button = QPushButton("▶ Phát audio")
        self.queue_preview_button.setEnabled(False)
        self.queue_preview_button.setToolTip(
            "Phát audio của hàng đã chọn bằng trình nghe nhạc mặc định của Windows."
        )
        self.delete_button = QPushButton("Xóa mục chọn")
        self.reset_button = QPushButton("Đặt lại")
        self.clear_button = QPushButton("Xóa tất cả")
        filter_row.addWidget(QLabel("Lọc:"))
        filter_row.addWidget(self.filter_combo)
        filter_row.addWidget(self.queue_search, 1)
        filter_row.addWidget(self.queue_preview_button)
        filter_row.addWidget(self.delete_button)
        filter_row.addWidget(self.reset_button)
        filter_row.addWidget(self.clear_button)
        layout.addLayout(filter_row)

        self.queue_model = QueueTableModel()
        self.queue_table = _DropTableView()
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_table.setItemDelegateForColumn(2, ProgressBarDelegate(self.queue_table))
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.queue_table, 1)
        self.queue_summary = QLabel("")
        self.queue_summary.setObjectName("hint")
        layout.addWidget(self.queue_summary)

        self.filter_combo.currentIndexChanged.connect(self._refresh_queue)
        self.queue_search.textChanged.connect(self._refresh_queue)
        self.delete_button.clicked.connect(self._delete_selected)
        self.reset_button.clicked.connect(self._reset_selected)
        self.clear_button.clicked.connect(self._clear_queue)
        self.queue_preview_button.clicked.connect(self._preview_selected_queue_audio)
        self.queue_table.paths_dropped.connect(self.queue.add_paths)
        self.queue_table.customContextMenuRequested.connect(self._queue_context_menu)
        self.queue_table.doubleClicked.connect(self._preview_queue_index)
        self.queue_table.selectionModel().selectionChanged.connect(
            self._update_queue_preview_button
        )
        return widget

    # --- Wiring -------------------------------------------------------------

    def _wire(self) -> None:
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        self.queue.items_changed.connect(self._refresh_queue)
        self.queue.log.connect(self.context.log)
        self.queue.worker_status.connect(self.context.set_worker_status)
        self.queue.progress.connect(self._on_queue_progress)
        self.queue.run_state_changed.connect(self._on_run_state)
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(400)
        self._settings_timer.timeout.connect(self._apply_settings_change)

    def _on_settings_changed(self) -> None:
        self._settings_timer.start()

    def _apply_settings_change(self) -> None:
        if self.settings_panel.current_model_id() != self._current_model_id:
            self._refresh_sidebar()
        if not self.queue.is_running():
            self.queue.mark_settings_outdated(self.settings_panel.current_settings())
        # Persist after the same short debounce used for queue invalidation, so
        # changing a spin box survives an app crash/restart instead of waiting
        # until the main window closes normally.
        data = self.context.preferences.load()
        self.save_preferences(data)
        self.context.preferences.save(data)

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

    def _update_queue_preview_button(self, *_args) -> None:
        item = self._selected_queue_item()
        self.queue_preview_button.setEnabled(
            bool(item and item.status == FileQueueStatus.DONE)
        )

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
        self._update_queue_preview_button()
        total = sum(counts.values())
        done = counts.get(FileQueueStatus.DONE, 0)
        failed = counts.get(FileQueueStatus.FAILED, 0)
        self.queue_summary.setText(
            f"Hiển thị {len(items)}/{total} · Thành công {done} · Lỗi {failed}"
        )

    def _queue_context_menu(self, position) -> None:
        index = self.queue_table.indexAt(position)
        item = self.queue_model.item_at(index.row()) if index.isValid() else None
        menu = QMenu(self)
        if item and item.status == FileQueueStatus.DONE:
            menu.addAction("▶ Phát audio", lambda: self._preview_queue_audio(item))
            menu.addAction("Mở thư mục kết quả", lambda: self._open_result(item))
            menu.addAction("Copy đường dẫn kết quả", lambda: self._copy_result(item))
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

    def _open_result(self, item) -> None:
        paths = item.output_manifest.paths_for("all")
        if paths:
            open_path(paths[0])

    def _copy_result(self, item) -> None:
        from PySide6.QtWidgets import QApplication

        paths = self.queue.collect_paths([item.item_id], "all")
        if paths:
            QApplication.clipboard().setText("\n".join(str(p) for p in paths))
            self.context.log("Đã copy đường dẫn kết quả.")

    # --- Running ------------------------------------------------------------

    def _run_queue(self, scope: str) -> None:
        settings = self.settings_panel.current_settings()
        self.queue.run(scope, settings, self._selected_item_ids())

    def _cancel(self) -> None:
        self.queue.cancel()

    def _on_queue_progress(self, percent: float, message: str) -> None:
        if percent < 0:
            self.progress_bar.setVisible(False)
            self.job_label.setText("Sẵn sàng")
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(int(max(0.0, min(1.0, percent)) * 100))
        self.job_label.setText(message)

    def _on_run_state(self, running: bool) -> None:
        self.cancel_button.setEnabled(running)
        for button in (self.run_button, self.run_selected_button, self.retry_button):
            button.setEnabled(not running)

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
        self._last_text_result = None
        self.text_preview_button.setEnabled(False)
        self._text_worker = GenerationWorker(self.ctrl, "text", settings, text=text)
        self._text_worker.progress_event.connect(self._on_text_progress)
        self._text_worker.completed.connect(self._on_text_done)
        self._text_worker.failed.connect(self._on_text_failed)
        self._text_worker.cancelled.connect(self._on_text_cancelled)
        self.generate_button.setEnabled(False)
        self.text_cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.context.set_worker_status("processing", "Đang tạo giọng đọc…")
        self.result_view.setPlainText("Đang xử lý…")
        self._text_worker.start()

    def _cancel_text(self) -> None:
        if self._text_worker is not None:
            self._text_worker.request_cancel()

    def _on_text_progress(self, event) -> None:
        percent = (event.current / event.total) if event.total else 0.0
        self.progress_bar.setValue(int(max(0.0, min(1.0, percent)) * 100))
        self.job_label.setText(event.message)
        self.context.log(event.message)

    def _on_text_done(self, result) -> None:
        self._last_text_result = result
        self.text_preview_button.setEnabled(True)
        self.result_view.setPlainText(labels.format_result(result))
        self._finish_text("ready", "Đã tạo giọng đọc.")

    def _on_text_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"Lỗi: {message}")
        self._finish_text("error", "Tạo giọng thất bại.")
        if "license" in message.lower() or "License" in message:
            self.context.show_page("license")

    def _on_text_cancelled(self) -> None:
        self.result_view.setPlainText("Đã hủy.")
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
        self.progress_bar.setVisible(False)
        self.job_label.setText("Sẵn sàng")
        self.context.set_worker_status(status, message)
        self.context.log(message)
        self._text_worker = None

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
