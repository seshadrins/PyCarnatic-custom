"""
Tabular Notation Editor (.ctab)
- Smart grid that auto-adjusts columns for the selected Thaalam & Jaathi
- Each avartam is one table row; each akshara cell has a note + lyric line
- Supports New, Open, Save, Delete row, and Play
"""
import os
import re
import copy
import zipfile
import time as _time
import threading
import xml.etree.ElementTree as ET
from PyQt6.QtCore import Qt, QTimer, QEvent, QItemSelectionModel
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QWidget, QSizePolicy, QFileDialog,
    QMessageBox, QHeaderView, QAbstractItemView, QFrame, QCheckBox, QSpinBox,
)
from PyQt6.QtGui import QColor, QFont
from carnatic import settings, cparser, cmidi
from carnatic import ctab_parser
from carnatic import raaga as raaga_module

# ──────────────────────────────────────────────────
# Anga colour palette
# ──────────────────────────────────────────────────
_ANGA_COLORS = {
    'L': QColor(173, 216, 230),   # light-blue  – Laghu
    'D': QColor(144, 238, 144),   # light-green – Drutam
    'A': QColor(255, 215, 0),     # gold        – Anudrutam
}
_NOTE_BG  = QColor(255, 255, 255)
_LYRIC_BG = QColor(255, 255, 204)
_HIGHLIGHT_NOTE_BG  = QColor(255, 215, 0)    # gold for active note
_HIGHLIGHT_LYRIC_BG = QColor(255, 193, 7)    # amber for active lyric
_HEADER_FIXED_COLS = 3   # Section | Speed | Bar
# Six characters are required for common tied four-slot patterns such as
# `,G3M1,`.  Keep a little extra room so the trailing continuation marker is
# never silently discarded while the user is typing.
_DEFAULT_NOTE_CELL_MAX_CHARS = 8
_TRANSITION_CELL_MAX_CHARS = 5
_TRANSITION_CELL_WIDTH = 45
_TRANSITION_BG = QColor(230, 245, 255)
_HIGHLIGHT_TRANSITION_BG = QColor(255, 230, 128)
_TRANSITION_AKSHARA_FRACTION = 0.25

# Kattai (Shruti) → MIDI base note for Sa
_KATTAI_TO_BASE_NOTE = {
    "1.0": "C4",  "1.5": "C#4", "2.0": "D4",  "2.5": "D#4",
    "3.0": "E4",  "4.0": "F4",  "4.5": "F#4", "5.0": "G4",
    "5.5": "G#4", "6.0": "A4",  "6.5": "A#4",
}


# ──────────────────────────────────────────────────
# _CellLineEdit – keyboard-navigable QLineEdit
# ──────────────────────────────────────────────────
class _CellLineEdit(QLineEdit):
    """QLineEdit that routes Tab / Shift-Tab / Arrow keys through the editor."""

    def __init__(self, field_type: str, cell_ref, parent=None):
        super().__init__(parent)
        self.field_type = field_type   # 'note' or 'lyric'
        self.cell_ref = cell_ref       # owning NoteCell

    def focusNextPrevChild(self, _next: bool) -> bool:  # noqa: ARG002
        """Return False so Qt does not consume Tab before keyPressEvent."""
        return False

    def keyPressEvent(self, event):
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        editor = self.cell_ref.editor_ref

        if editor is None:
            super().keyPressEvent(event)
            return

        row = self.cell_ref.table_row
        col = self.cell_ref.table_col

        # Tab / Shift-Tab – move cell-to-cell within same row, then next/prev row.
        # Works for both note and lyric fields (stays in the same field type).
        if key == Qt.Key.Key_Tab:
            if not shift:
                editor._navigate_cell_same_row(row, col, +1, self.field_type)
            else:
                editor._navigate_cell_same_row(row, col, -1, self.field_type)
            event.accept()
            return

        # Enter/Return – note→lyric (same cell); lyric→next note (wraps rows)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.field_type == 'note':
                self.cell_ref.lyric_edit.setFocus()   # note → lyric same cell
            else:
                editor._navigate_cell(row, col, +1, 'note')  # lyric → next cell
            event.accept()
            return

        # Up / Down – move between rows, same column & field
        if key == Qt.Key.Key_Down:
            editor._navigate_row(row, col, self.field_type, +1)
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            editor._navigate_row(row, col, self.field_type, -1)
            event.accept()
            return

        # Left / Right on empty field – move between fields / cells
        if key == Qt.Key.Key_Right and not self.text():
            if self.field_type == 'note':
                self.cell_ref.lyric_edit.setFocus()
            else:
                editor._navigate_cell(row, col, +1, 'note')
            event.accept()
            return
        if key == Qt.Key.Key_Left and not self.text():
            if self.field_type == 'lyric':
                self.cell_ref.note_edit.setFocus()
            else:
                editor._navigate_cell(row, col, -1, 'lyric')
            event.accept()
            return

        super().keyPressEvent(event)


# ──────────────────────────────────────────────────
# NoteCell – stacked note + lyric QLineEdits
# ──────────────────────────────────────────────────
class NoteCell(QWidget):
    """One akshara cell with a note field (top) and lyric field (bottom).
    Supports Tab/Arrow navigation and smart swara resolution."""

    def focusNextPrevChild(self, _next: bool) -> bool:
        """Prevent Qt's focus chain from consuming Tab at the widget level."""
        return False

    def __init__(self, anga_type: str = 'L', max_chars: int = 5, parent=None):
        super().__init__(parent)
        self.anga_type = anga_type
        # Navigation context – filled by TabularEditorDialog after insertion
        self.table_row: int = -1
        self.table_col: int = -1
        self.editor_ref = None   # type: TabularEditorDialog

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # Note input (top half) – uses navigable line-edit
        self.note_edit = _CellLineEdit('note', self)
        self.note_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note_edit.setMaxLength(max_chars)
        self.note_edit.setToolTip("Enter note (e.g. S, R, P, D, S', -). "
                                  "Auto-resolves to raaga variant on Tab/Enter.")
        self.note_edit.setStyleSheet(
            f"background-color: {_NOTE_BG.name()}; border: none;")
        layout.addWidget(self.note_edit)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Lyric input (bottom half)
        self.lyric_edit = _CellLineEdit('lyric', self)
        self.lyric_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyric_edit.setMaxLength(max_chars)
        self.lyric_edit.setToolTip("Enter lyric syllable")
        self.lyric_edit.setStyleSheet(
            f"background-color: {_LYRIC_BG.name()}; border: none;")
        layout.addWidget(self.lyric_edit)

        # Tint the widget border with anga colour
        color = _ANGA_COLORS.get(anga_type, _NOTE_BG)
        self.setStyleSheet(
            f"NoteCell {{ border: 1px solid {color.name()}; }}")

        # Auto-resolve note when editing finishes
        self.note_edit.editingFinished.connect(self._auto_resolve_note)

    def _auto_resolve_note(self):
        """Resolve a generic swara (e.g. 'R') to its raaga-specific variant."""
        if self.editor_ref:
            raw = self.note_edit.text().strip()
            resolved = self.editor_ref._resolve_note(
                raw, self.table_row, self.table_col)
            if resolved != raw:
                if len(resolved) > self.note_edit.maxLength():
                    self.note_edit.setMaxLength(len(resolved))
                self.note_edit.setText(resolved)

    # Convenience accessors
    def note(self) -> str:
        return self.note_edit.text().strip()

    def lyric(self) -> str:
        return self.lyric_edit.text().strip()

    def set_note(self, text: str):
        self.note_edit.setText(text)

    def set_lyric(self, text: str):
        self.lyric_edit.setText(text)


# ──────────────────────────────────────────────────
# _SepWidget – thin visual separator between avartam groups
# ──────────────────────────────────────────────────
class TransitionCell(QWidget):
    """Optional crossover swara between two akshara cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table_row: int = -1
        self.table_col: int = -1
        self.editor_ref = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.edit = QLineEdit()
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setMaxLength(_TRANSITION_CELL_MAX_CHARS)
        self.edit.setToolTip(
            "Optional transition swara; use , to continue the previous swara")
        self.edit.setStyleSheet(
            f"background-color: {_TRANSITION_BG.name()}; border: none;")
        layout.addWidget(self.edit)
        self.setStyleSheet("TransitionCell { border: 1px solid #b8d7e8; }")
        self.edit.editingFinished.connect(self._auto_resolve_transition)

    def _auto_resolve_transition(self):
        if self.editor_ref:
            raw = self.edit.text().strip()
            resolved = self.editor_ref._resolve_note(
                raw, self.table_row, self.table_col)
            if resolved != raw:
                if len(resolved) > self.edit.maxLength():
                    self.edit.setMaxLength(len(resolved))
                self.edit.setText(resolved)

    def transition(self) -> str:
        return self.edit.text().strip()

    def set_transition(self, text: str):
        self.edit.setText(text)


class _SepWidget(QWidget):
    """Narrow dark bar that visually separates avartam groups in the grid."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #5a5a5a;")
        self.setFixedWidth(6)


# ──────────────────────────────────────────────────
# TabularEditorDialog
# ──────────────────────────────────────────────────
class TabularEditorDialog(QDialog):
    """
    Full tabular notation editor dialog.
    Pass an MPlayer instance for playback support.
    """

    def __init__(self, parent=None, mplayer=None, player_type=None,
                 include_percussion: bool = True):
        super().__init__(parent)
        self.mplayer = mplayer
        self.player_type = player_type or settings._PLAYER_TYPE
        self.include_percussion = include_percussion
        self._filepath = ""
        self._data = ctab_parser.create_empty_data()
        self._note_map: dict = {}          # combined base-note → specific variant
        self._aro_note_map: dict = {}      # aarohanam-specific note map
        self._avro_note_map: dict = {}     # avarohanam-specific note map
        self._current_raaga_id = None      # int raaga index from raaga module
        self._cmn_editor = None            # reference to CMN TutorUI window
        self._avartams_per_line: int = 1   # how many avartams to show per display row
        self._show_transitions: bool = False
        self._max_chars_per_cell: int = _DEFAULT_NOTE_CELL_MAX_CHARS
        self._aksharas_per_avartam: int = 8  # filled by _rebuild_grid
        self._row_clipboard: list[dict] = []
        self._row_clipboard_shape: tuple | None = None

        # Playback cell-highlighting support
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setInterval(30)   # ~33 fps – tight enough for smooth sync
        self._highlight_timer.timeout.connect(self._update_highlight)
        self._timing_map: list = []             # [(start_sec, row, col), ...]
        self._row_transitions: list = []        # [(start_sec, row)] – one entry per new row
        self._play_start_time: float = 0.0
        self._last_highlighted: tuple = (-1, -1)
        self._manual_scroll_until: float = 0.0  # briefly suspend auto-follow after user scrolling
        self._last_auto_scroll_row: int = -1   # prevent repeated no-op scrollTo calls
        self._timing_index: int = -1           # incremental playback timing cursor
        self._row_transition_index: int = -1   # incremental auto-scroll cursor
        self._scamp_is_playing: bool = False

        self.setWindowTitle("Tabular Notation Editor (.ctab)")
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._rebuild_grid()

    # ── UI Construction ────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # 1. Metadata panel
        root.addWidget(self._create_metadata_panel())

        # 2. Playback settings bar (Instrument / Shruti / Drums)
        root.addWidget(self._create_playback_panel())

        # 3. Anga structure info label
        self._anga_label = QLabel()
        self._anga_label.setStyleSheet("font-style: italic; color: #444;")
        root.addWidget(self._anga_label)

        # 4. Button bar
        btn_bar = QHBoxLayout()
        self._btn_add = QPushButton("+ Add Avartam")
        self._btn_del = QPushButton("✕ Delete Row")
        self._btn_del.setText("✕ Delete Row(s)")
        self._btn_copy = QPushButton("Copy Row(s)")
        self._btn_paste = QPushButton("Paste Row(s)")
        self._btn_paste.setEnabled(False)
        self._btn_new = QPushButton("New")
        self._btn_open = QPushButton("Open…")
        self._btn_save = QPushButton("Save")
        self._btn_save_as = QPushButton("Save As…")
        self._btn_import_cmn = QPushButton("Import CMN…")
        self._btn_import_csv = QPushButton("Import CSV…")
        self._btn_export_csv = QPushButton("Export…")
        self._btn_play = QPushButton("▶ Play")
        self._btn_stop = QPushButton("■ Stop")
        self._btn_cmn = QPushButton("Open CMN Editor…")
        self._btn_close = QPushButton("Close")
        for btn in [self._btn_add, self._btn_del,
                    self._btn_copy, self._btn_paste, self._btn_new,
                    self._btn_open, self._btn_save, self._btn_save_as,
                    self._btn_import_cmn, self._btn_import_csv,
                    self._btn_export_csv,
                    self._btn_play, self._btn_stop,
                    self._btn_cmn, self._btn_close]:
            btn_bar.addWidget(btn)
        root.addLayout(btn_bar)

        # 5. Table
        self._table = QTableWidget()
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setTabKeyNavigation(False)   # our _CellLineEdit handles Tab
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(52)
        self._table.installEventFilter(self)
        self._table.viewport().installEventFilter(self)
        self._table.verticalScrollBar().installEventFilter(self)
        root.addWidget(self._table)

        # Connections
        self._btn_add.clicked.connect(self._add_avartam_row)
        self._btn_del.clicked.connect(self._delete_selected_row)
        self._btn_copy.clicked.connect(self._copy_selected_rows)
        self._btn_paste.clicked.connect(self._paste_copied_rows)
        self._btn_new.clicked.connect(self._new_file)
        self._btn_open.clicked.connect(self._open_file)
        self._btn_save.clicked.connect(self._save_file)
        self._btn_save_as.clicked.connect(self._save_as_file)
        self._btn_import_cmn.clicked.connect(self._import_cmn_file)
        self._btn_import_csv.clicked.connect(self._import_csv)
        self._btn_export_csv.clicked.connect(self._export_spreadsheet)
        self._btn_play.clicked.connect(self._play)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_cmn.clicked.connect(self._open_cmn_editor)
        self._btn_close.clicked.connect(self.close)

    def eventFilter(self, watched, event):
        """Give manual scrolling a short grace period before playback follows again."""
        if (hasattr(self, '_table')
                and watched in (self._table, self._table.viewport())
                and event.type() == QEvent.Type.KeyPress):
            modifiers = event.modifiers()
            if (modifiers & Qt.KeyboardModifier.ControlModifier
                    and event.key() == Qt.Key.Key_C):
                self._copy_selected_rows()
                event.accept()
                return True
            if (modifiers & Qt.KeyboardModifier.ControlModifier
                    and event.key() == Qt.Key.Key_V):
                self._paste_copied_rows()
                event.accept()
                return True
            if (modifiers == Qt.KeyboardModifier.NoModifier
                    and event.key() == Qt.Key.Key_Delete):
                self._delete_selected_row()
                event.accept()
                return True

        if (hasattr(self, '_table')
                and watched in (self._table.viewport(),
                                self._table.verticalScrollBar())):
            scrolling_keys = {
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End,
            }
            is_manual_scroll = event.type() in (
                QEvent.Type.Wheel, QEvent.Type.MouseButtonPress,
                QEvent.Type.TouchBegin,
            )
            if (event.type() == QEvent.Type.KeyPress
                    and event.key() in scrolling_keys):
                is_manual_scroll = True
            if is_manual_scroll:
                self._manual_scroll_until = _time.monotonic() + 2.0
                self._last_auto_scroll_row = -1
        return super().eventFilter(watched, event)

    # ── Metadata Panel ─────────────────────────────
    def _create_metadata_panel(self) -> QGroupBox:
        box = QGroupBox("Composition Information")
        form = QFormLayout(box)

        self._meta_type = QComboBox()
        self._meta_type.addItems(ctab_parser.COMPOSITION_TYPES)
        form.addRow("Type:", self._meta_type)

        self._meta_title = QLineEdit()
        form.addRow("Title:", self._meta_title)

        # Ragam – searchable dropdown
        self._meta_ragam = QComboBox()
        self._meta_ragam.setEditable(True)
        self._meta_ragam.addItems(raaga_module.get_raaga_list())
        self._meta_ragam.setCurrentIndex(-1)
        self._meta_ragam.setPlaceholderText("Select or type a Raaga…")
        form.addRow("Ragam:", self._meta_ragam)

        # Melakartha – auto-filled from raaga selection (read-only)
        self._meta_mela = QLineEdit()
        self._meta_mela.setMaximumWidth(60)
        self._meta_mela.setReadOnly(True)
        form.addRow("Melakartha #:", self._meta_mela)

        # Aarohanam row with Play Scale button
        aro_widget = QWidget()
        aro_layout = QHBoxLayout(aro_widget)
        aro_layout.setContentsMargins(0, 0, 0, 0)
        self._meta_aarohanam_label = QLabel("—")
        self._meta_aarohanam_label.setStyleSheet(
            "font-weight: bold; color: #003399; font-size: 11px;")
        self._meta_aarohanam_label.setWordWrap(True)
        self._btn_play_scale = QPushButton("▶ Play Scale")
        self._btn_play_scale.setMaximumWidth(110)
        aro_layout.addWidget(self._meta_aarohanam_label, stretch=1)
        aro_layout.addWidget(self._btn_play_scale)
        form.addRow("Aarohanam:", aro_widget)

        # Avarohanam row
        self._meta_avarohanam_label = QLabel("—")
        self._meta_avarohanam_label.setStyleSheet(
            "font-weight: bold; color: #990033; font-size: 11px;")
        self._meta_avarohanam_label.setWordWrap(True)
        form.addRow("Avarohanam:", self._meta_avarohanam_label)

        # Thaalam & Jaathi on the same row
        tj_widget = QWidget()
        tj_layout = QHBoxLayout(tj_widget)
        tj_layout.setContentsMargins(0, 0, 0, 0)
        self._meta_thaalam = QComboBox()
        self._meta_thaalam.addItems(
            [t.name for t in settings.THAALA_NAMES])
        self._meta_jaathi = QComboBox()
        self._meta_jaathi.addItems(
            [j.name for j in settings.JAATHI_NAMES])
        tj_layout.addWidget(QLabel("Thaalam:"))
        tj_layout.addWidget(self._meta_thaalam)
        tj_layout.addWidget(QLabel("  Jaathi:"))
        tj_layout.addWidget(self._meta_jaathi)
        tj_layout.addStretch()
        form.addRow("", tj_widget)

        # Avartams per display line
        apl_widget = QWidget()
        apl_layout = QHBoxLayout(apl_widget)
        apl_layout.setContentsMargins(0, 0, 0, 0)
        self._spin_avartams_per_line = QSpinBox()
        self._spin_avartams_per_line.setRange(1, 8)
        self._spin_avartams_per_line.setValue(1)
        self._spin_avartams_per_line.setMaximumWidth(60)
        self._spin_avartams_per_line.setToolTip(
            "Number of avartams shown per display row.\n"
            "Useful for short thaalams (e.g. Eka) or CMN files with\n"
            "multiple avartams per line. CTAB file always stores one per row.")
        apl_layout.addWidget(self._spin_avartams_per_line)
        apl_layout.addStretch()
        form.addRow("Avartams/line:", apl_widget)

        self._chk_show_transitions = QCheckBox("Show transition cells")
        self._chk_show_transitions.setToolTip(
            "Show the optional transition-swara column after each note cell.")
        form.addRow("Transitions:", self._chk_show_transitions)

        self._spin_max_chars_per_cell = QSpinBox()
        self._spin_max_chars_per_cell.setRange(1, 30)
        self._spin_max_chars_per_cell.setValue(_DEFAULT_NOTE_CELL_MAX_CHARS)
        self._spin_max_chars_per_cell.setMaximumWidth(60)
        self._spin_max_chars_per_cell.setToolTip(
            "Maximum characters allowed in each note cell; the column width "
            "is adjusted to match.")
        form.addRow("Max chars/cell:", self._spin_max_chars_per_cell)

        # Tempo
        self._meta_tempo = QLineEdit("60")
        self._meta_tempo.setMaximumWidth(60)
        form.addRow("Tempo (BPM):", self._meta_tempo)

        self._meta_composer = QLineEdit()
        form.addRow("Composer:", self._meta_composer)

        self._meta_language = QComboBox()
        self._meta_language.addItems(ctab_parser.LANGUAGES)
        form.addRow("Language:", self._meta_language)

        self._meta_description = QLineEdit()
        form.addRow("Description:", self._meta_description)

        # Signal connections
        self._meta_thaalam.currentIndexChanged.connect(self._rebuild_grid)
        self._meta_jaathi.currentIndexChanged.connect(self._rebuild_grid)
        self._meta_ragam.currentTextChanged.connect(self._on_raaga_changed)
        self._btn_play_scale.clicked.connect(self._play_scale)
        self._spin_avartams_per_line.valueChanged.connect(
            self._on_avartams_per_line_changed)
        self._chk_show_transitions.toggled.connect(
            self._on_show_transitions_changed)
        self._spin_max_chars_per_cell.valueChanged.connect(
            self._on_max_chars_per_cell_changed)

        # Pre-populate from _DEFAULT_META – block signals so _rebuild_grid
        # is not triggered before _anga_label and the rest of _setup_ui exist.
        self._meta_thaalam.blockSignals(True)
        self._meta_jaathi.blockSignals(True)
        self._meta_ragam.blockSignals(True)
        self._populate_metadata_panel(ctab_parser._DEFAULT_META)
        self._meta_thaalam.blockSignals(False)
        self._meta_jaathi.blockSignals(False)
        self._meta_ragam.blockSignals(False)
        return box

    def _populate_metadata_panel(self, meta: dict):
        self._meta_type.setCurrentText(meta.get('Type', 'Geetham'))
        self._meta_title.setText(meta.get('Title', ''))
        self._meta_ragam.setCurrentText(meta.get('Ragam', ''))
        # Melakartha is auto-filled when raaga changes; only set directly if not empty
        if meta.get('Melakartha', ''):
            self._meta_mela.setText(meta.get('Melakartha', ''))
        thaalam_name = meta.get('Thaalam', 'THRIPUTAI')
        jaathi_name = meta.get('Jaathi', 'CHATHUSRA')
        self._meta_thaalam.setCurrentText(thaalam_name)
        self._meta_jaathi.setCurrentText(jaathi_name)
        self._meta_tempo.setText(meta.get('Tempo', '60'))
        self._meta_composer.setText(meta.get('Composer', ''))
        self._meta_language.setCurrentText(meta.get('Language', 'Sanskrit'))
        self._meta_description.setText(meta.get('Description', ''))
        # Avartams per line – block signal so _rebuild_grid isn't called twice
        try:
            apl = max(1, int(meta.get('AvartamsPerLine', '1') or '1'))
        except ValueError:
            apl = 1
        self._avartams_per_line = apl
        self._spin_avartams_per_line.blockSignals(True)
        self._spin_avartams_per_line.setValue(apl)
        self._spin_avartams_per_line.blockSignals(False)
        show_value = str(meta.get('ShowTransitions', 'False')).strip().lower()
        self._show_transitions = show_value in ('1', 'true', 'yes', 'on')
        self._chk_show_transitions.blockSignals(True)
        self._chk_show_transitions.setChecked(self._show_transitions)
        self._chk_show_transitions.blockSignals(False)
        try:
            max_chars = int(meta.get(
                'MaxCharsPerCell', str(_DEFAULT_NOTE_CELL_MAX_CHARS))
                or str(_DEFAULT_NOTE_CELL_MAX_CHARS))
        except ValueError:
            max_chars = _DEFAULT_NOTE_CELL_MAX_CHARS
        self._max_chars_per_cell = max(1, max_chars)
        self._spin_max_chars_per_cell.blockSignals(True)
        self._spin_max_chars_per_cell.setMaximum(
            max(30, self._max_chars_per_cell))
        self._spin_max_chars_per_cell.setValue(self._max_chars_per_cell)
        self._spin_max_chars_per_cell.blockSignals(False)

    def _read_metadata_from_panel(self) -> dict:
        return {
            'Type': self._meta_type.currentText(),
            'Title': self._meta_title.text().strip(),
            'Ragam': self._meta_ragam.currentText().strip(),
            'Melakartha': self._meta_mela.text().strip(),
            'Thaalam': self._meta_thaalam.currentText(),
            'Jaathi': self._meta_jaathi.currentText(),
            'Tempo': self._meta_tempo.text().strip(),
            'Composer': self._meta_composer.text().strip(),
            'Language': self._meta_language.currentText(),
            'Description': self._meta_description.text().strip(),
            'AvartamsPerLine': str(self._avartams_per_line),
            'ShowTransitions': str(self._show_transitions),
            'MaxCharsPerCell': str(self._max_chars_per_cell),
        }

    def _on_avartams_per_line_changed(self, value: int):
        """Called when the Avartams/line spinbox changes. Rebuilds the grid."""
        self._avartams_per_line = max(1, value)
        self._rebuild_grid()

    def _on_show_transitions_changed(self, checked: bool):
        """Show or hide transition columns while preserving their contents."""
        self._show_transitions = checked
        for ci, atype in enumerate(self._col_anga_types):
            if atype == 'T':
                self._table.setColumnHidden(_HEADER_FIXED_COLS + ci, not checked)

    def _on_max_chars_per_cell_changed(self, value: int):
        """Apply the input limit and compact width to current note cells."""
        self._max_chars_per_cell = max(1, value)
        width = max(45, self._max_chars_per_cell * 9 + 12)
        for ci, atype in enumerate(self._col_anga_types):
            if atype not in ('SEP', 'T'):
                col = _HEADER_FIXED_COLS + ci
                self._table.setColumnWidth(col, width)
                for row in range(1, self._table.rowCount()):
                    cell = self._table.cellWidget(row, col)
                    if isinstance(cell, NoteCell):
                        cell.note_edit.setMaxLength(self._max_chars_per_cell)
                        cell.lyric_edit.setMaxLength(self._max_chars_per_cell)

    # ── Playback Settings Panel ────────────────────
    def _create_playback_panel(self) -> QGroupBox:
        """Instrument / Shruti (Kattai) / Drums bar."""
        box = QGroupBox("Playback Settings")
        row = QHBoxLayout(box)
        row.setContentsMargins(6, 4, 6, 4)

        # Instrument
        row.addWidget(QLabel("Instrument:"))
        self._pb_instrument = QComboBox()
        inst_list = list(settings._CARNATIC_INSTRUMENTS + settings._DEFAULT_INSTRUMENTS)
        self._pb_instrument.addItems(inst_list)
        self._pb_instrument.setCurrentText(settings.CURRENT_INSTRUMENT)
        row.addWidget(self._pb_instrument)

        row.addWidget(QLabel("  Shruti (Kattai):"))
        self._pb_kattai = QComboBox()
        self._pb_kattai.addItems(settings.KATTAI_LIST)
        self._pb_kattai.setCurrentText("4.5")   # common default
        row.addWidget(self._pb_kattai)

        row.addWidget(QLabel("  Drums:"))
        self._pb_drums_on = QComboBox()
        self._pb_drums_on.addItems(["Off"] + list(settings._PERCUSSION_INSTRUMENTS))
        if self.include_percussion:
            self._pb_drums_on.setCurrentText(settings.CURRENT_PERCUSSION_INSTRUMENT)
        else:
            self._pb_drums_on.setCurrentIndex(0)
        row.addWidget(self._pb_drums_on)

        # Smart (direction-aware) swara resolution toggle
        self._chk_smart_resolve = QCheckBox("↕ Direction-aware resolve")
        self._chk_smart_resolve.setToolTip(
            "When checked, swara auto-resolution uses the preceding note's\n"
            "pitch to pick the aarohanam or avarohanam variant automatically.")
        self._chk_smart_resolve.setChecked(True)
        row.addWidget(self._chk_smart_resolve)

        row.addStretch()

        # Wire up signals
        self._pb_instrument.currentTextChanged.connect(self._on_instrument_changed)
        self._pb_kattai.currentTextChanged.connect(self._on_kattai_changed)
        self._pb_drums_on.currentTextChanged.connect(self._on_drums_changed)
        return box

    def _on_instrument_changed(self, name: str):
        settings.CURRENT_INSTRUMENT = name
        settings.INSTRUMENT_INDEX = settings._get_list_index(
            name, list(settings._CARNATIC_INSTRUMENTS + settings._DEFAULT_INSTRUMENTS))

    def _on_kattai_changed(self, kattai: str):
        base_note = _KATTAI_TO_BASE_NOTE.get(kattai)
        if base_note:
            # Update base note for ALL melodic instruments so the shift is heard
            for i in range(len(settings.INSTRUMENT_BASE_NOTES)):
                settings.INSTRUMENT_BASE_NOTES[i] = base_note

    def _on_drums_changed(self, value: str):
        if value == "Off":
            self.include_percussion = False
        else:
            self.include_percussion = True
            settings.CURRENT_PERCUSSION_INSTRUMENT = value
            settings.CURRENT_PERCUSSION_INDEX = settings._get_list_index(
                value, list(settings._PERCUSSION_INSTRUMENTS))

    # ── Grid Build ─────────────────────────────────
    def _current_thaala_jaathi(self):
        t_name = self._meta_thaalam.currentText()
        j_name = self._meta_jaathi.currentText()
        ti = ctab_parser.get_thaala_index(t_name)
        ji = ctab_parser.get_jaathi_index(j_name)
        return ti, ji

    def _rebuild_grid(self):
        """Rebuild table columns for the current Thaalam + Jaathi."""
        ti, ji = self._current_thaala_jaathi()
        self._anga_struct = ctab_parser.get_anga_structure(ti, ji)
        aks = sum(s for _, _, s in self._anga_struct)
        self._aksharas_per_avartam = aks
        n = self._avartams_per_line
        note_cell_width = max(45, self._max_chars_per_cell * 9 + 12)

        # Update anga info label
        parts = [f"{name}({size})" for name, _, size in self._anga_struct]
        self._anga_label.setText(
            "  Structure: " + " | ".join(parts) +
            f"  =  {aks} aksharas/avartam  ×  {n} avartam(s)/line")

        # Collect existing grid data before destroying it
        existing = self._collect_grid_rows() if self._table.rowCount() > 1 else []

        # Build columns: each main akshara has a following transition cell.
        self._col_anga_types = []
        self._col_header_labels = []
        self._col_group_labels = []
        for av in range(n):
            if av > 0:
                self._col_anga_types.append('SEP')
                self._col_header_labels.append('||')
                self._col_group_labels.append('')
            for full, col_lbl, size in self._anga_struct:
                for i in range(size):
                    prefix = f"[{av+1}]" if n > 1 else ""
                    atype = col_lbl[0]
                    self._col_anga_types.append(atype)
                    self._col_header_labels.append(f"{prefix}{col_lbl}[{i+1}]")
                    self._col_group_labels.append(
                        f"[{av+1}]{full}" if n > 1 and i == 0
                        else (full if i == 0 else ""))
                    self._col_anga_types.append('T')
                    self._col_header_labels.append('T')
                    self._col_group_labels.append('T')

        total_cols = _HEADER_FIXED_COLS + len(self._col_anga_types)
        self._table.setColumnCount(total_cols)
        base_types = []  # old width/header loops are overridden below

        # Build column headers
        headers = ['Section', 'Speed', 'Bar']
        for av in range(n):
            if av > 0:
                headers.append('║')
            for _, col_lbl, size in self._anga_struct:
                for i in range(size):
                    prefix = f"[{av+1}]" if n > 1 else ""
                    headers.append(f"{prefix}{col_lbl}[{i+1}]")
        headers = ['Section', 'Speed', 'Bar'] + self._col_header_labels
        self._table.setHorizontalHeaderLabels(headers)

        # Column widths + header colors
        for c in range(_HEADER_FIXED_COLS):
            self._table.setColumnWidth(c, 100 if c == 0 else 60)
        ci = 0
        for av in range(n):
            if av > 0:
                self._table.setColumnWidth(_HEADER_FIXED_COLS + ci, 6)
                ci += 1
            for atype in base_types:
                col = _HEADER_FIXED_COLS + ci
                self._table.setColumnWidth(col, note_cell_width)
                hdr = self._table.horizontalHeaderItem(col)
                if hdr:
                    hdr.setBackground(_ANGA_COLORS.get(atype, _NOTE_BG))
                ci += 1

        # Row 0 – anga header labels (read-only)
        self._table.clearSpans()
        self._table.clearSpans()
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            if atype == 'SEP':
                self._table.setColumnWidth(col, 6)
            elif atype == 'T':
                self._table.setColumnWidth(col, _TRANSITION_CELL_WIDTH)
                hdr = self._table.horizontalHeaderItem(col)
                if hdr:
                    hdr.setBackground(_TRANSITION_BG)
            else:
                self._table.setColumnWidth(col, note_cell_width)
                hdr = self._table.horizontalHeaderItem(col)
                if hdr:
                    hdr.setBackground(_ANGA_COLORS.get(atype, _NOTE_BG))

        for ci, atype in enumerate(self._col_anga_types):
            self._table.setColumnHidden(
                _HEADER_FIXED_COLS + ci,
                atype == 'T' and not self._show_transitions)

        self._table.setRowCount(1)
        self._table.clearSpans()
        self._table.setRowHeight(0, 22)
        for c in range(_HEADER_FIXED_COLS):
            item = QTableWidgetItem(['Section', 'Speed', 'Bar'][c])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setBackground(QColor(200, 200, 200))
            self._table.setItem(0, c, item)
        col_start = _HEADER_FIXED_COLS
        for av in range(n):
            if av > 0:
                sep_item = QTableWidgetItem('')
                sep_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                sep_item.setBackground(QColor(90, 90, 90))
                self._table.setItem(0, col_start, sep_item)
                col_start += 1
            for full, col_lbl, size in self._anga_struct:
                atype = col_lbl[0]
                color = _ANGA_COLORS.get(atype, _NOTE_BG)
                for i in range(size):
                    lbl = (f"[{av+1}]{full}" if n > 1 and i == 0
                           else (full if i == 0 else ""))
                    item = QTableWidgetItem(lbl)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setBackground(color)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    bold_font = QFont()
                    bold_font.setBold(True)
                    item.setFont(bold_font)
                    self._table.setItem(0, col_start, item)
                    col_start += 1
                if size > 1:
                    self._table.setSpan(0, col_start - size, 1, size)

        self._table.clearSpans()
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            if atype == 'SEP':
                item = QTableWidgetItem('')
                item.setBackground(QColor(90, 90, 90))
            else:
                item = QTableWidgetItem(self._col_group_labels[ci])
                item.setBackground(
                    _TRANSITION_BG if atype == 'T'
                    else _ANGA_COLORS.get(atype, _NOTE_BG))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bold_font = QFont()
            bold_font.setBold(True)
            item.setFont(bold_font)
            self._table.setItem(0, col, item)

        # Re-populate existing display rows
        for row_data in existing:
            self._insert_row_from_data(row_data)
        self._renumber_bars()

    def _add_avartam_row(self):
        """Insert an empty avartam row.

        If any data rows are selected the new row is inserted immediately after
        the last selected row; otherwise it is appended at the end.
        """
        selected = sorted(
            self._selected_data_rows())
        insert_at = selected[-1] + 1 if selected else self._table.rowCount()
        self._insert_avartam_at(insert_at)
        self._renumber_bars()
        self._select_rows([insert_at])

    def _insert_avartam_at(self, r: int):
        """Insert a blank display row at table row index *r* and refresh refs.

        The bar number shown in column 2 is the first avartam number of this
        display row: (data_rows_before * N) + 1, where data_rows_before is the
        number of display rows already in the table before position r.
        """
        # r=1 is the first data row (row 0 is the anga header).
        # data_rows_before = number of data rows above the insertion point.
        data_rows_before = r - 1
        starting_bar = data_rows_before * self._avartams_per_line + 1
        self._table.insertRow(r)
        self._table.setRowHeight(r, 52)
        self._init_fixed_cells(r, bar=str(starting_bar))
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            if atype == 'SEP':
                self._table.setCellWidget(r, col, _SepWidget())
            elif atype == 'T':
                cell = TransitionCell()
                cell.editor_ref = self
                cell.table_row = r
                cell.table_col = col
                self._table.setCellWidget(r, col, cell)
            else:
                cell = NoteCell(atype, self._max_chars_per_cell)
                cell.editor_ref = self
                cell.table_row = r
                cell.table_col = col
                self._table.setCellWidget(r, col, cell)
        self._refresh_cell_refs()

    def _refresh_cell_refs(self):
        """Update table_row / table_col on every NoteCell after structural changes."""
        for r in range(1, self._table.rowCount()):
            for ci, atype in enumerate(self._col_anga_types):
                if atype == 'SEP':
                    continue
                col = _HEADER_FIXED_COLS + ci
                cell = self._table.cellWidget(r, col)
                if isinstance(cell, (NoteCell, TransitionCell)):
                    cell.table_row = r
                    cell.table_col = col

    def _insert_row_from_data(self, note_lyric_pair: dict,
                              row: int | None = None):
        """Insert a display row from notes, transitions, and lyrics.

        The flat lists hold all N avartams' data
        concatenated (SEP columns are not counted).
        """
        r = self._table.rowCount() if row is None else row
        self._table.insertRow(r)
        self._table.setRowHeight(r, 52)
        self._init_fixed_cells(r,
                               note_lyric_pair.get('section', ''),
                               note_lyric_pair.get('speed', '1'),
                               note_lyric_pair.get('bar', ''))
        notes = note_lyric_pair.get('notes', [])
        transitions = note_lyric_pair.get('transitions', [])
        lyrics = note_lyric_pair.get('lyrics', [])
        data_ci = 0   # index into notes/transitions/lyrics, skipping SEP slots
        trans_ci = 0
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            if atype == 'SEP':
                self._table.setCellWidget(r, col, _SepWidget())
                continue
            if atype == 'T':
                cell = TransitionCell()
                cell.editor_ref = self
                cell.table_row = r
                cell.table_col = col
                if trans_ci < len(transitions):
                    cell.set_transition(transitions[trans_ci])
                self._table.setCellWidget(r, col, cell)
                trans_ci += 1
                continue
            cell = NoteCell(atype, self._max_chars_per_cell)
            cell.editor_ref = self
            cell.table_row = r
            cell.table_col = col
            if data_ci < len(notes):
                cell.set_note(notes[data_ci])
            if data_ci < len(lyrics):
                cell.set_lyric(lyrics[data_ci])
            self._table.setCellWidget(r, col, cell)
            data_ci += 1
        self._refresh_cell_refs()

    def _init_fixed_cells(self, row: int,
                          section: str = '', speed: str = '1', bar: str = ''):
        # Section dropdown
        section_combo = QComboBox()
        section_combo.addItems(ctab_parser.SECTION_NAMES)
        if section:
            section_combo.setCurrentText(section)
        self._table.setCellWidget(row, 0, section_combo)

        # Speed dropdown
        speed_combo = QComboBox()
        speed_combo.addItems(ctab_parser.SPEED_NAMES)
        if speed:
            speed_combo.setCurrentText(str(speed))
        self._table.setCellWidget(row, 1, speed_combo)

        # Bar number (auto from position, editable)
        bar_val = bar if bar else str(row)
        bar_item = QTableWidgetItem(bar_val)
        bar_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 2, bar_item)

    def _selected_data_rows(self) -> list[int]:
        """Return unique selected data rows in visual order."""
        selection = self._table.selectionModel()
        if selection is None:
            return []
        return sorted(
            index.row() for index in selection.selectedRows() if index.row() > 0)

    def _row_shape(self) -> tuple:
        """Describe the grid shape required by a copied row payload."""
        return (
            self._avartams_per_line,
            self._aksharas_per_avartam,
            tuple(self._col_anga_types),
        )

    def _renumber_bars(self):
        """Number each display row by the first avartam it contains."""
        for row in range(1, self._table.rowCount()):
            starting_bar = (
                (row - 1) * self._avartams_per_line + 1)
            item = self._table.item(row, 2)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2, item)
            item.setText(str(starting_bar))

    def _select_rows(self, rows: list[int]):
        """Replace the selection with the supplied valid data rows."""
        self._table.clearSelection()
        selection = self._table.selectionModel()
        if selection is None:
            return
        flags = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows)
        valid_rows = [
            row for row in rows if 0 < row < self._table.rowCount()]
        if valid_rows:
            selection.setCurrentIndex(
                self._table.model().index(valid_rows[0], 2),
                QItemSelectionModel.SelectionFlag.NoUpdate)
        for row in valid_rows:
            selection.select(self._table.model().index(row, 0), flags)

    def _delete_selected_row(self):
        rows = self._selected_data_rows()
        if not rows:
            return
        first_deleted = rows[0]
        for row in reversed(rows):
            self._table.removeRow(row)
        self._refresh_cell_refs()
        self._renumber_bars()
        if self._table.rowCount() > 1:
            self._select_rows([
                min(first_deleted, self._table.rowCount() - 1)])

    def _copy_selected_rows(self):
        rows = self._selected_data_rows()
        if not rows:
            return
        grid_rows = self._collect_grid_rows()
        self._row_clipboard = copy.deepcopy(
            [grid_rows[row - 1] for row in rows])
        self._row_clipboard_shape = self._row_shape()
        self._btn_paste.setEnabled(True)

    def _paste_copied_rows(self):
        if not self._row_clipboard:
            return
        if self._row_clipboard_shape != self._row_shape():
            QMessageBox.warning(
                self, "Cannot Paste Rows",
                "The copied rows do not match the current Thaalam, Jaathi, "
                "or Avartams Per Line grid.")
            return

        selected = self._selected_data_rows()
        insert_at = (
            selected[-1] + 1 if selected else self._table.rowCount())
        pasted_rows = []
        for offset, row_data in enumerate(
                copy.deepcopy(self._row_clipboard)):
            row = insert_at + offset
            self._insert_row_from_data(row_data, row=row)
            pasted_rows.append(row)
        self._refresh_cell_refs()
        self._renumber_bars()
        self._select_rows(pasted_rows)

    # ── Collect Data from Grid ─────────────────────
    def _collect_grid_rows(self) -> list:
        """Return one dict per display row. Notes, transitions, and lyrics are flat
        lists with all N avartams concatenated; SEP columns are skipped."""
        result = []
        for r in range(1, self._table.rowCount()):
            sec_w = self._table.cellWidget(r, 0)
            spd_w = self._table.cellWidget(r, 1)
            bar_i = self._table.item(r, 2)
            section = sec_w.currentText() if sec_w else ''
            speed = spd_w.currentText() if spd_w else '1'
            bar = bar_i.text() if bar_i else str(r)
            notes, transitions, lyrics = [], [], []
            for ci, atype in enumerate(self._col_anga_types):
                if atype == 'SEP':
                    continue
                cell = self._table.cellWidget(r, _HEADER_FIXED_COLS + ci)
                if isinstance(cell, NoteCell):
                    notes.append(cell.note())
                    lyrics.append(cell.lyric())
                elif isinstance(cell, TransitionCell):
                    transitions.append(cell.transition())
                else:
                    notes.append('')
                    lyrics.append('')
            result.append({'section': section, 'speed': speed,
                           'bar': bar, 'notes': notes,
                           'transitions': transitions, 'lyrics': lyrics})
        return result

    def _collect_data(self) -> dict:
        """Build a ctab data dict – one CTAB row per avartam (not per display row).

        Bar numbers are assigned by a global sequential counter (1, 2, 3, …)
        so they are always unique across all display rows regardless of what
        the UI bar column shows.  This prevents key collisions during reload.
        """
        data = {'meta': self._read_metadata_from_panel(), 'rows': []}
        n = self._avartams_per_line
        aks = self._aksharas_per_avartam
        global_bar = 1   # ever-increasing; never clashes between display rows
        for rd in self._collect_grid_rows():
            notes_flat = rd['notes']    # length = n * aks
            transitions_flat = rd.get('transitions', [])
            lyrics_flat = rd['lyrics']
            for i in range(n):
                chunk_notes  = (notes_flat[i*aks:(i+1)*aks]
                                + [''] * aks)[:aks]
                chunk_transitions = (transitions_flat[i*aks:(i+1)*aks]
                                     + [''] * aks)[:aks]
                chunk_lyrics = (lyrics_flat[i*aks:(i+1)*aks]
                                + [''] * aks)[:aks]
                bar = str(global_bar)
                global_bar += 1
                data['rows'].append({
                    'section': rd['section'], 'speed': rd['speed'],
                    'bar': bar, 'row_type': 'N', 'aksharas': chunk_notes,
                })
                # Hidden transitions mean "no transitions" for the persisted
                # score.  Do not retain stale T rows merely because their
                # editor widgets still contain values from an earlier state.
                if (self._show_transitions
                        and any(tr.strip() for tr in chunk_transitions)):
                    data['rows'].append({
                        'section': rd['section'], 'speed': rd['speed'],
                        'bar': bar, 'row_type': 'T',
                        'aksharas': chunk_transitions,
                    })
                if any(lyr.strip() for lyr in chunk_lyrics):
                    data['rows'].append({
                        'section': rd['section'], 'speed': rd['speed'],
                        'bar': bar, 'row_type': 'L', 'aksharas': chunk_lyrics,
                    })
        return data

    def _populate_grid_from_data(self, data: dict):
        """Populate the grid from a loaded ctab data dict.

        The CTAB file stores one avartam per row.  When AvartamsPerLine > 1
        consecutive rows are grouped into a single display row.
        """
        # QLineEdit truncates text immediately when setText() exceeds its
        # maxLength.  Determine the required size before creating any cells so
        # opening/importing a composition can never discard note or lyric text.
        longest_loaded_cell = max(
            (len(str(value))
             for row in data.get('rows', [])
             if row.get('row_type', 'N') in ('N', 'L')
             for value in row.get('aksharas', [])),
            default=0,
        )
        try:
            configured_max = int(data.get('meta', {}).get(
                'MaxCharsPerCell', str(_DEFAULT_NOTE_CELL_MAX_CHARS))
                or str(_DEFAULT_NOTE_CELL_MAX_CHARS))
        except ValueError:
            configured_max = _DEFAULT_NOTE_CELL_MAX_CHARS
        required_max = max(
            _DEFAULT_NOTE_CELL_MAX_CHARS, configured_max, longest_loaded_cell)
        data.setdefault('meta', {})['MaxCharsPerCell'] = str(required_max)

        # Transition rows are the source of truth.  Older CTAB files predate
        # the ShowTransitions metadata option, so automatically reveal the
        # transition columns whenever at least one saved transition is present.
        has_saved_transitions = any(
            row.get('row_type', 'N') == 'T'
            and any(str(value).strip()
                    for value in row.get('aksharas', []))
            for row in data.get('rows', []))
        if has_saved_transitions:
            data['meta']['ShowTransitions'] = 'True'

        # Read AvartamsPerLine from metadata BEFORE _rebuild_grid
        try:
            apl = max(1, int(data['meta'].get('AvartamsPerLine', '1') or '1'))
        except ValueError:
            apl = 1
        self._avartams_per_line = apl
        self._populate_metadata_panel(data['meta'])   # also sets _avartams_per_line + spinbox
        self._rebuild_grid()

        # Pair note, transition, and lyric rows by (section, speed, bar) key
        note_map, transition_map, lyric_map, order = {}, {}, {}, []
        for row in data['rows']:
            key = (row.get('section', ''), row.get('speed', '1'),
                   row.get('bar', '1'))
            row_type = row.get('row_type', 'N')
            if row_type == 'N':
                note_map[key] = row.get('aksharas', [])
                if key not in order:
                    order.append(key)
            elif row_type == 'T':
                transition_map[key] = row.get('aksharas', [])
            else:
                lyric_map[key] = row.get('aksharas', [])

        # Group N consecutive CTAB rows into one display row
        n = self._avartams_per_line
        i = 0
        while i < len(order):
            group = order[i:i + n]
            combined_notes, combined_transitions, combined_lyrics = [], [], []
            for key in group:
                combined_notes.extend(note_map.get(key, []))
                combined_transitions.extend(transition_map.get(key, []))
                combined_lyrics.extend(lyric_map.get(key, []))
            sec, spd, bar = group[0]
            self._insert_row_from_data({
                'section': sec, 'speed': spd, 'bar': bar,
                'notes': combined_notes, 'transitions': combined_transitions,
                'lyrics': combined_lyrics,
            })
            i += n
        self._renumber_bars()

    # ── File Operations ────────────────────────────
    def _new_file(self):
        self._filepath = ""
        self._data = ctab_parser.create_empty_data()
        # Clear all rows so _rebuild_grid starts fresh (not re-populating old data)
        self._table.setRowCount(0)
        self._populate_metadata_panel(ctab_parser._DEFAULT_META)
        self._rebuild_grid()
        self.setWindowTitle("Tabular Notation Editor – New File")

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Tabular Notation File",
            settings._LESSONS_PATH,
            "Carnatic Tabular (*.ctab);;All Files (*)")
        if not path:
            return
        try:
            data = ctab_parser.read_ctab(path)
            self._filepath = path
            self._data = data
            self._table.setRowCount(0)   # clear old rows before loading
            self._populate_grid_from_data(data)
            self.setWindowTitle(
                f"Tabular Notation Editor – {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e))

    def _save_file(self):
        if not self._filepath:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Tabular Notation File",
                settings._LESSONS_PATH,
                "Carnatic Tabular (*.ctab);;All Files (*)")
            if not path:
                return
            if not path.endswith('.ctab'):
                path += '.ctab'
            self._filepath = path
        try:
            data = self._collect_data()
            ctab_parser.write_ctab(data, self._filepath)
            self.setWindowTitle(
                f"Tabular Notation Editor – {os.path.basename(self._filepath)}")
            QMessageBox.information(self, "Saved",
                                    f"File saved:\n{self._filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _save_as_file(self):
        """Always open a Save dialog to choose a new location."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As – Tabular Notation File",
            self._filepath or settings._LESSONS_PATH,
            "Carnatic Tabular (*.ctab);;All Files (*)")
        if not path:
            return
        if not path.endswith('.ctab'):
            path += '.ctab'
        self._filepath = path
        try:
            data = self._collect_data()
            ctab_parser.write_ctab(data, self._filepath)
            self.setWindowTitle(
                f"Tabular Notation Editor – {os.path.basename(self._filepath)}")
            QMessageBox.information(self, "Saved",
                                    f"File saved:\n{self._filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _import_cmn_file(self):
        """Open a .cmn file and convert it to tabular notation."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CMN File",
            settings._LESSONS_PATH,
            "Carnatic Notation (*.cmn);;All Files (*)")
        if not path:
            return
        try:
            data = ctab_parser.convert_cmn_to_ctab(path)
            self._filepath = ""
            self._table.setRowCount(0)
            self._populate_grid_from_data(data)
            base = os.path.basename(path)
            self.setWindowTitle(f"Tabular Notation Editor – {base} [imported]")
            QMessageBox.information(
                self, "Import Complete",
                f"Imported from:\n{path}\n\n"
                "Review the notation and use 'Save As…' to save as a .ctab file.")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _import_csv(self):
        """Import a CSV exported by this editor.

        CSV carries grid contents, not full composition metadata. The current
        metadata panel provides thaalam, jaathi, raaga, tempo, and other fields.
        """
        import csv as _csv
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CSV",
            settings._LESSONS_PATH,
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        try:
            with open(path, 'r', newline='', encoding='utf-8-sig') as f:
                rows_in = list(_csv.DictReader(f))
            if not rows_in:
                QMessageBox.warning(self, "Import CSV", "No data rows found.")
                return

            fieldnames = rows_in[0].keys()
            av_nums = []
            for name in fieldnames:
                m = re.match(r"Av(\d+)_[NTL](\d+)$", name or "")
                if m:
                    av_nums.append(int(m.group(1)))
            n = max(av_nums) if av_nums else self._avartams_per_line
            n = max(1, n)

            ti, ji = self._current_thaala_jaathi()
            aks = ctab_parser.get_total_aksharas(ti, ji)
            meta = self._read_metadata_from_panel()
            meta['AvartamsPerLine'] = str(n)
            data = {'meta': meta, 'rows': []}

            global_bar = 1
            for csv_row in rows_in:
                section = (csv_row.get('Section') or '').strip()
                speed = (csv_row.get('Speed') or '1').strip()
                for av in range(1, n + 1):
                    notes, transitions, lyrics = [], [], []
                    for i in range(1, aks + 1):
                        notes.append((csv_row.get(f"Av{av}_N{i}") or '').strip())
                        transitions.append((csv_row.get(f"Av{av}_T{i}") or '').strip())
                        lyrics.append((csv_row.get(f"Av{av}_L{i}") or '').strip())

                    bar = str(global_bar)
                    global_bar += 1
                    data['rows'].append({
                        'section': section, 'speed': speed, 'bar': bar,
                        'row_type': 'N', 'aksharas': notes,
                    })
                    if any(t.strip() for t in transitions):
                        data['rows'].append({
                            'section': section, 'speed': speed, 'bar': bar,
                            'row_type': 'T', 'aksharas': transitions,
                        })
                    if any(l.strip() for l in lyrics):
                        data['rows'].append({
                            'section': section, 'speed': speed, 'bar': bar,
                            'row_type': 'L', 'aksharas': lyrics,
                        })

            self._filepath = ""
            self._table.setRowCount(0)
            self._populate_grid_from_data(data)
            self.setWindowTitle(
                f"Tabular Notation Editor - {os.path.basename(path)} [imported]")
            QMessageBox.information(self, "Import Complete",
                                    f"Imported CSV:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Import CSV Error", str(e))

    _EXPORT_SWARA_RE = re.compile(
        r"([SP]|[RGMDN][1-4]?)([.']?)(?:~[1-4]?)?")

    @classmethod
    def _clean_swara_for_export(cls, value: str) -> str:
        """Remove swara variants and gamakas without altering other notation."""
        def _clean(match):
            token = match.group(1)
            return token[0] + match.group(2)

        return cls._EXPORT_SWARA_RE.sub(_clean, str(value))

    def _build_csv_rows(self) -> list[list[str]]:
        """Build export rows, omitting entirely blank transition/lyric columns."""
        n = self._avartams_per_line
        aks = self._aksharas_per_avartam
        grid_rows = self._collect_grid_rows()
        slot_count = n * aks

        include_transition = [
            any(
                idx < len(row.get('transitions', []))
                and str(row['transitions'][idx]).strip()
                for row in grid_rows)
            for idx in range(slot_count)
        ]
        include_lyric = [
            any(
                idx < len(row.get('lyrics', []))
                and str(row['lyrics'][idx]).strip()
                for row in grid_rows)
            for idx in range(slot_count)
        ]

        header = ['Section', 'Speed', 'Bar']
        for av in range(n):
            if av > 0:
                header.append('')
            for i in range(aks):
                idx = av * aks + i
                header.append(f"Av{av+1}_N{i+1}")
                if include_transition[idx]:
                    header.append(f"Av{av+1}_T{i+1}")
                if include_lyric[idx]:
                    header.append(f"Av{av+1}_L{i+1}")

        rows_out = [header]
        for row in grid_rows:
            notes = row.get('notes', [])
            transitions = row.get('transitions', [])
            lyrics = row.get('lyrics', [])
            row_out = [row['section'], row['speed'], row['bar']]
            for av in range(n):
                if av > 0:
                    row_out.append('')
                for i in range(aks):
                    idx = av * aks + i
                    note = notes[idx] if idx < len(notes) else ''
                    row_out.append(self._clean_swara_for_export(note))
                    if include_transition[idx]:
                        transition = (
                            transitions[idx] if idx < len(transitions) else '')
                        row_out.append(
                            self._clean_swara_for_export(transition))
                    if include_lyric[idx]:
                        row_out.append(
                            lyrics[idx] if idx < len(lyrics) else '')
            rows_out.append(row_out)
        return rows_out

    def _build_excel_sheets(self) -> list[tuple[str, list[list[str]]]]:
        """Build separate Notes and Lyrics worksheet data."""
        n = self._avartams_per_line
        aks = self._aksharas_per_avartam
        grid_rows = self._collect_grid_rows()
        slot_count = n * aks

        include_transition = [
            any(
                idx < len(row.get('transitions', []))
                and str(row['transitions'][idx]).strip()
                for row in grid_rows)
            for idx in range(slot_count)
        ]
        include_lyric = [
            any(
                idx < len(row.get('lyrics', []))
                and str(row['lyrics'][idx]).strip()
                for row in grid_rows)
            for idx in range(slot_count)
        ]

        notes_header = ['Section', 'Speed', 'Bar']
        for av in range(n):
            if av > 0:
                notes_header.append('')
            for i in range(aks):
                idx = av * aks + i
                notes_header.append(f"Av{av+1}_N{i+1}")
                if include_transition[idx]:
                    notes_header.append(f"Av{av+1}_T{i+1}")

        notes_rows = [notes_header]
        for row in grid_rows:
            notes = row.get('notes', [])
            transitions = row.get('transitions', [])
            output = [row['section'], row['speed'], row['bar']]
            for av in range(n):
                if av > 0:
                    output.append('')
                for i in range(aks):
                    idx = av * aks + i
                    note = notes[idx] if idx < len(notes) else ''
                    output.append(self._clean_swara_for_export(note))
                    if include_transition[idx]:
                        transition = (
                            transitions[idx] if idx < len(transitions) else '')
                        output.append(
                            self._clean_swara_for_export(transition))
            notes_rows.append(output)

        sheets = [('Notes', notes_rows)]
        if any(include_lyric):
            lyrics_header = ['Section', 'Speed', 'Bar']
            for av in range(n):
                included = [
                    i for i in range(aks)
                    if include_lyric[av * aks + i]]
                if not included:
                    continue
                if len(lyrics_header) > 3:
                    lyrics_header.append('')
                lyrics_header.extend(
                    f"Av{av+1}_L{i+1}" for i in included)

            lyrics_rows = [lyrics_header]
            for row in grid_rows:
                lyrics = row.get('lyrics', [])
                output = [row['section'], row['speed'], row['bar']]
                wrote_avartam = False
                for av in range(n):
                    included = [
                        i for i in range(aks)
                        if include_lyric[av * aks + i]]
                    if not included:
                        continue
                    if wrote_avartam:
                        output.append('')
                    output.extend(
                        lyrics[av * aks + i]
                        if av * aks + i < len(lyrics) else ''
                        for i in included)
                    wrote_avartam = True
                lyrics_rows.append(output)
            sheets.append(('Lyrics', lyrics_rows))
        return sheets

    @staticmethod
    def _excel_column_name(number: int) -> str:
        """Convert a one-based column number to an Excel column name."""
        result = ''
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    @classmethod
    def _worksheet_xml(cls, rows: list[list[str]]) -> bytes:
        """Create a minimal OOXML worksheet using inline strings."""
        namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        ET.register_namespace('', namespace)
        worksheet = ET.Element(f'{{{namespace}}}worksheet')
        sheet_data = ET.SubElement(worksheet, f'{{{namespace}}}sheetData')
        for row_number, values in enumerate(rows, 1):
            row_element = ET.SubElement(
                sheet_data, f'{{{namespace}}}row',
                {'r': str(row_number)})
            for column_number, value in enumerate(values, 1):
                text = str(value)
                cell = ET.SubElement(
                    row_element, f'{{{namespace}}}c',
                    {
                        'r': (
                            f'{cls._excel_column_name(column_number)}'
                            f'{row_number}'),
                        't': 'inlineStr',
                    })
                inline = ET.SubElement(cell, f'{{{namespace}}}is')
                text_element = ET.SubElement(inline, f'{{{namespace}}}t')
                if text != text.strip():
                    text_element.set(
                        '{http://www.w3.org/XML/1998/namespace}space',
                        'preserve')
                text_element.text = text
        return ET.tostring(
            worksheet, encoding='utf-8', xml_declaration=True)

    @classmethod
    def _write_xlsx(cls, path: str,
                    sheets: list[tuple[str, list[list[str]]]]):
        """Write a dependency-free XLSX workbook containing the given sheets."""
        main_ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel_ns = (
            'http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships')
        package_rel_ns = (
            'http://schemas.openxmlformats.org/package/2006/relationships')
        content_ns = (
            'http://schemas.openxmlformats.org/package/2006/content-types')
        ET.register_namespace('', main_ns)
        ET.register_namespace('r', rel_ns)

        workbook = ET.Element(f'{{{main_ns}}}workbook')
        workbook_sheets = ET.SubElement(workbook, f'{{{main_ns}}}sheets')
        for index, (name, _) in enumerate(sheets, 1):
            ET.SubElement(
                workbook_sheets, f'{{{main_ns}}}sheet',
                {
                    'name': name,
                    'sheetId': str(index),
                    f'{{{rel_ns}}}id': f'rId{index}',
                })

        workbook_rels = ET.Element(f'{{{package_rel_ns}}}Relationships')
        for index in range(1, len(sheets) + 1):
            ET.SubElement(
                workbook_rels, f'{{{package_rel_ns}}}Relationship',
                {
                    'Id': f'rId{index}',
                    'Type': (
                        f'{rel_ns}/worksheet'),
                    'Target': f'worksheets/sheet{index}.xml',
                })

        root_rels = ET.Element(f'{{{package_rel_ns}}}Relationships')
        ET.SubElement(
            root_rels, f'{{{package_rel_ns}}}Relationship',
            {
                'Id': 'rId1',
                'Type': f'{rel_ns}/officeDocument',
                'Target': 'xl/workbook.xml',
            })

        content_types = ET.Element(f'{{{content_ns}}}Types')
        ET.SubElement(
            content_types, f'{{{content_ns}}}Default',
            {
                'Extension': 'rels',
                'ContentType': (
                    'application/vnd.openxmlformats-package.'
                    'relationships+xml'),
            })
        ET.SubElement(
            content_types, f'{{{content_ns}}}Default',
            {'Extension': 'xml', 'ContentType': 'application/xml'})
        ET.SubElement(
            content_types, f'{{{content_ns}}}Override',
            {
                'PartName': '/xl/workbook.xml',
                'ContentType': (
                    'application/vnd.openxmlformats-officedocument.'
                    'spreadsheetml.sheet.main+xml'),
            })
        for index in range(1, len(sheets) + 1):
            ET.SubElement(
                content_types, f'{{{content_ns}}}Override',
                {
                    'PartName': f'/xl/worksheets/sheet{index}.xml',
                    'ContentType': (
                        'application/vnd.openxmlformats-officedocument.'
                        'spreadsheetml.worksheet+xml'),
                })

        xml = lambda element: ET.tostring(
            element, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(
                path, 'w', compression=zipfile.ZIP_DEFLATED) as workbook_zip:
            workbook_zip.writestr('[Content_Types].xml', xml(content_types))
            workbook_zip.writestr('_rels/.rels', xml(root_rels))
            workbook_zip.writestr('xl/workbook.xml', xml(workbook))
            workbook_zip.writestr(
                'xl/_rels/workbook.xml.rels', xml(workbook_rels))
            for index, (_, rows) in enumerate(sheets, 1):
                workbook_zip.writestr(
                    f'xl/worksheets/sheet{index}.xml',
                    cls._worksheet_xml(rows))

    def _export_spreadsheet(self):
        """Export either CSV or a multi-sheet XLSX workbook."""
        import csv as _csv
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Spreadsheet",
            (self._filepath.replace('.ctab', '') if self._filepath
             else settings._LESSONS_PATH),
            "Excel Workbook (*.xlsx);;CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        lower_path = path.lower()
        export_csv = (
            lower_path.endswith('.csv')
            or ('CSV Files' in selected_filter
                and not lower_path.endswith('.xlsx')))
        if export_csv:
            if not lower_path.endswith('.csv'):
                path += '.csv'
        elif not lower_path.endswith('.xlsx'):
            path += '.xlsx'

        try:
            self._renumber_bars()
            if export_csv:
                with open(
                        path, 'w', newline='', encoding='utf-8-sig') as file:
                    _csv.writer(file).writerows(self._build_csv_rows())
            else:
                self._write_xlsx(path, self._build_excel_sheets())

            QMessageBox.information(self, "Exported",
                                    f"Spreadsheet saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Playback ───────────────────────────────────
    def _play(self):
        if (not self.mplayer
                and self.player_type != settings.PLAYER_TYPE.SCAMP):
            QMessageBox.warning(self, "No Player",
                                "No MPlayer instance available.")
            return
        try:
            # Apply tempo to settings so write_to_midifile uses the right BPM
            try:
                settings.TEMPO = float(self._meta_tempo.text() or '60')
            except ValueError:
                settings.TEMPO = 60.0

            scamp_notes, self._timing_map, perc_list = self._build_scamp_and_timing()
            has_gamaka = any('~' in str(note) for note, _ in scamp_notes)
            use_scamp = (has_gamaka
                         or self.player_type == settings.PLAYER_TYPE.SCAMP)

            # Build row-transition schedule: one entry each time the active
            # row changes.  Used by _update_highlight to pre-scroll the next
            # row into view ~300 ms before the highlight reaches it.
            self._row_transitions = []
            _last_rt_row = -1
            for (start, trow, _tcol) in self._timing_map:
                if trow != _last_rt_row:
                    self._row_transitions.append((start, trow))
                    _last_rt_row = trow

            temp_midi = settings._TEMP_PATH + "tabular_play.mid"
            if not use_scamp:
                cmidi.write_to_midifile_from_scamp_notes(
                    scamp_notes, temp_midi,
                    include_percussion_layer=self.include_percussion,
                    solkattu_list=perc_list if self.include_percussion else None)

            if self.mplayer:
                self.mplayer.is_playing = True
            self._scamp_is_playing = use_scamp
            self._btn_play.setEnabled(False)
            # _play_start_time stays None until the on_audio_start callback
            # fires inside MPlayer.play_midi_file – right between synthesis and
            # the actual play_sound call.  The highlight timer returns early
            # (via the None guard below) during the synthesis phase, then starts
            # tracking from the moment the first audio sample is emitted.
            self._play_start_time = None
            self._last_highlighted = (-1, -1)
            self._last_auto_scroll_row = -1
            self._timing_index = -1
            self._row_transition_index = -1
            self._highlight_timer.start()

            def _bg():
                try:
                    if use_scamp:
                        # MIDI/SF2 cannot render SCAMP pitch envelopes.  Use
                        # SCAMP automatically for a tabular score containing a
                        # kampitam marker, even when MIDI is the normal player.
                        from carnatic import cplayer
                        self._play_start_time = _time.monotonic()
                        # The normal MIDI player stores velocity as 0..127;
                        # SCAMP expects amplitude as 0.0..1.0.
                        old_volumes = list(settings._INSTRUMENT_VOLUME_LEVELS)
                        try:
                            settings._INSTRUMENT_VOLUME_LEVELS[:] = [
                                min(1.0, float(v) / settings._VOLUME_MAX)
                                if float(v) > 1.0 else float(v)
                                for v in old_volumes]
                            cplayer.play_notes(
                                scamp_notes,
                                include_percussion_layer=self.include_percussion,
                                solkattu_list=(perc_list
                                               if self.include_percussion else None))
                        finally:
                            settings._INSTRUMENT_VOLUME_LEVELS[:] = old_volumes
                        return

                    def _on_audio_start():
                        # Called by MPlayer right before play_sound(); this is
                        # the closest possible point to actual audio emission.
                        self._play_start_time = _time.monotonic()

                    self.mplayer.play_midi_file(temp_midi,
                                                on_audio_start=_on_audio_start)
                except Exception as ex:
                    print("Playback error:", ex)
                finally:
                    self._scamp_is_playing = False
                    if self.mplayer:
                        self.mplayer.is_playing = False
                    # The highlight timer performs Qt widget updates on the
                    # main thread; touching the button from here is unsafe.

            threading.Thread(target=_bg, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "Play Error", str(e))

    def _stop(self):
        self._highlight_timer.stop()
        self._clear_all_highlights()
        if self.mplayer:
            self.mplayer.stop()
            self._btn_play.setEnabled(True)

    # ── Direct CTAB → MIDI engine ─────────────────
    # Tokeniser: extracts individual swara tokens from a cell's note text.
    # Supports concatenated or space-separated tokens, e.g. "D2G3'" or "D2 G3'".
    # Handles uppercase notes only (S/P without digit; R/G/M/D/N with optional digit 1-4).
    # A trailing ~ (optionally followed by a 1-4 neighbour distance) requests
    # kampitam, e.g. D2~ or D2~2.
    # Octave markers: '.' (lower) or "'" (upper).  '^' is intentionally excluded
    # (S^ notation is no longer supported). Trailing glide marker '-' is not
    # captured so G3- tokenises as G3 (glide is a visual cue only in MIDI mode).
    _TOKEN_RE = re.compile(
        r"([SP][.']?(?:~[1-4]?)?|[RGMDN][1-4]?[.']?(?:~[1-4]?)?|[,;])")

    @classmethod
    def _tokenize_note_cell(cls, note_text: str) -> list:
        return cls._TOKEN_RE.findall(note_text.replace(' ', ''))

    @staticmethod
    def _token_slot_count(tokens: list) -> int:
        slots = 0
        for tok in tokens:
            slots += 2 if tok == ';' else 1
        return slots

    def _build_scamp_and_timing(self) -> tuple:
        """Build SCAMP note list, timing map, and percussion list from the grid.

        Returns:
            scamp_notes  – list of [note_name, [inst_idx, pitch_float, duration_beats]]
            timing_map   – list of (start_sec, table_row, table_col) for every
                           visible cell, including rests and continuations.
            perc_list    – one beat entry per akshara, ready to pass as
                           solkattu_list to write_to_midifile_from_scamp_notes.
        """
        tempo     = settings.TEMPO            # already applied by _play
        full_dur  = settings._FULL_NOTE_DURATION   # beats per akshara at speed-1
        inst      = settings.INSTRUMENT_INDEX
        silent_inst = len(settings._ALL_INSTRUMENTS)
        perc_inst = getattr(settings, 'CURRENT_PERCUSSION_INDEX', 0)
        # Standard GM percussion pitch 38 = acoustic snare; sounds on most SoundFonts
        PERC_PITCH = 38

        scamp_notes: list = []
        timing_map:  list = []
        perc_list:   list = []
        current_time = 0.0   # seconds (for timing_map)

        # Gamaka neighbour lookup must follow the rāga selected in this editor,
        # not whichever rāga happened to be used elsewhere in the application.
        if self._current_raaga_id is not None:
            raaga_module.set_default_raaga_id(self._current_raaga_id)

        def _pitch_for_token(token: str):
            """Return a fixed pitch or a SCAMP kampitam Envelope."""
            if '~' not in token:
                return cparser._get_microtone_pitch(token)
            note, marker = token.split('~', 1)
            neighbour_distance = int(marker) if marker else 1
            pitch = cparser._kampitam(note, neighbour_distance)
            return (pitch if pitch is not None
                    else cparser._get_microtone_pitch(note))

        # Play only selected rows (if any), else play all data rows.
        selected_rows = {
            i.row() for i in self._table.selectedItems() if i.row() > 0}
        rows_to_play = (sorted(selected_rows)
                        if selected_rows
                        else list(range(1, self._table.rowCount())))

        def _append_segment(note_text: str, duration_beats: float,
                            duration_sec: float):
            nonlocal current_time
            note_text = (note_text or '').strip()
            if duration_beats <= 0:
                return
            if note_text in ('', '-'):
                scamp_notes.append(['$', [silent_inst, 60.0, duration_beats]])
                current_time += duration_sec
                return
            if note_text == ',':
                if scamp_notes:
                    scamp_notes[-1][1][2] += duration_beats
                current_time += duration_sec
                return
            if note_text == ';':
                if scamp_notes:
                    scamp_notes[-1][1][2] += duration_beats
                current_time += duration_sec
                return

            tokens = self._tokenize_note_cell(note_text)
            slot_count = self._token_slot_count(tokens)
            if not tokens or slot_count <= 0:
                scamp_notes.append(['$', [silent_inst, 60.0, duration_beats]])
                current_time += duration_sec
                return

            token_beats = duration_beats / slot_count
            for tok in tokens:
                if tok == ',':
                    if scamp_notes:
                        scamp_notes[-1][1][2] += token_beats
                    continue
                if tok == ';':
                    if scamp_notes:
                        scamp_notes[-1][1][2] += 2 * token_beats
                    continue
                try:
                    pitch = _pitch_for_token(tok)
                    scamp_notes.append([tok, [inst, pitch, token_beats]])
                except Exception:
                    scamp_notes.append(['$', [silent_inst, 60.0, token_beats]])
            current_time += duration_sec

        pending_transition = ''
        for grid_row_idx in rows_to_play:
            spd_w = self._table.cellWidget(grid_row_idx, 1)
            try:
                speed = float(spd_w.currentText()) if spd_w else 1.0
            except (ValueError, AttributeError):
                speed = 1.0
            base_akshara_beats = full_dur / (2 ** (speed - 1))
            base_akshara_sec = base_akshara_beats * (60.0 / tempo)

            for ci, atype in enumerate(self._col_anga_types):
                if atype == 'SEP':
                    continue   # skip separator columns entirely
                col       = _HEADER_FIXED_COLS + ci
                cell      = self._table.cellWidget(grid_row_idx, col)
                if atype == 'T':
                    pending_transition = (
                        cell.transition().strip()
                        if isinstance(cell, TransitionCell) else '')
                    continue

                akshara_beats = base_akshara_beats
                akshara_sec = base_akshara_sec
                note_text = cell.note().strip() if isinstance(cell, NoteCell) else ''

                # One percussion beat per akshara (regardless of note content)
                perc_list.append(['beat', [perc_inst, PERC_PITCH, base_akshara_beats]])

                if pending_transition:
                    trans_beats = min(
                        base_akshara_beats * _TRANSITION_AKSHARA_FRACTION,
                        akshara_beats)
                    trans_sec = trans_beats * (60.0 / tempo)
                    _append_segment(pending_transition, trans_beats, trans_sec)
                    akshara_beats -= trans_beats
                    akshara_sec -= trans_sec
                    pending_transition = ''

                # Track every visible cell, including continuations and empty
                # cells.  Otherwise the amber marker appears frozen and rows
                # containing only continuations never enter the scroll schedule.
                timing_map.append((current_time, grid_row_idx, col))

                # ── Prolongation: , extends last note by 1 akshara ──────────
                if note_text == ',':
                    if scamp_notes:
                        scamp_notes[-1][1][2] += akshara_beats
                    current_time += akshara_sec
                    continue

                # ── Prolongation: ; extends last note by 2 aksharas ─────────
                if note_text == ';':
                    if scamp_notes:
                        scamp_notes[-1][1][2] += 2 * akshara_beats
                    # Add a second percussion beat for the extra akshara
                    perc_list.append(['beat', [perc_inst, PERC_PITCH, akshara_beats]])
                    current_time += 2 * akshara_sec
                    continue

                # ── Empty cell: continue the previous playable swara ─────────
                if not note_text:
                    if scamp_notes and scamp_notes[-1][0] != '$':
                        scamp_notes[-1][1][2] += akshara_beats
                        current_time += akshara_sec
                        continue

                    scamp_notes.append(['$', [silent_inst, 60.0, akshara_beats]])
                    current_time += akshara_sec
                    continue

                # ── Explicit rest cell ───────────────────────────────────────
                if note_text == '-':
                    scamp_notes.append(['$', [silent_inst, 60.0, akshara_beats]])
                    current_time += akshara_sec
                    continue

                # ── Note cell (single or multi-note) ────────────────────────
                tokens = self._tokenize_note_cell(note_text)
                if not tokens:
                    # Unrecognised content → rest
                    scamp_notes.append(['$', [silent_inst, 60.0, akshara_beats]])
                    current_time += akshara_sec
                    continue

                slot_count = self._token_slot_count(tokens)
                if slot_count <= 0:
                    scamp_notes.append(['$', [silent_inst, 60.0, akshara_beats]])
                    current_time += akshara_sec
                    continue

                token_beats = akshara_beats / slot_count
                for tok in tokens:
                    if tok == ',':
                        if scamp_notes:
                            scamp_notes[-1][1][2] += token_beats
                        continue
                    if tok == ';':
                        if scamp_notes:
                            scamp_notes[-1][1][2] += 2 * token_beats
                        continue
                    try:
                        pitch = _pitch_for_token(tok)
                        scamp_notes.append([tok, [inst, pitch, token_beats]])
                    except Exception:
                        # Unrecognised note → silence placeholder
                        scamp_notes.append(['$', [silent_inst, 60.0, token_beats]])

                current_time += akshara_sec

        return scamp_notes, timing_map, perc_list

    # ── Cell Highlighting ──────────────────────────

    # How far ahead (seconds) to check for an upcoming off-screen row.
    # 500 ms gives Qt enough time to finish the layout+repaint before the
    # highlight timer reaches the first cell of the newly scrolled-in row.
    _PRE_SCROLL_SEC = 0.5

    def _update_highlight(self):
        """Called by QTimer every ~30 ms during playback.

        Highlighting and scrolling are intentionally decoupled:

        * **Highlighting** (cell colour): plain stylesheet swap — no layout
          work, always fast.

        * **Scrolling**: proactive, deriving the target row from elapsed time.
          A scroll is issued only when the upcoming row
          is **not already visible** in the viewport.  If all rows fit on
          screen no scroll is ever issued.  When a scroll IS needed,
          ``PositionAtTop`` brings the new row to the top so several
          subsequent rows also become visible, avoiding repeated per-line
          scrolls for the rows that follow.
        """
        is_playing = (self._scamp_is_playing
                      or (self.mplayer and self.mplayer.is_playing))
        if not is_playing:
            self._highlight_timer.stop()
            self._clear_all_highlights()
            self._btn_play.setEnabled(True)
            return

        # Guard: synthesis is still running; _play_start_time not set yet.
        if self._play_start_time is None:
            return

        elapsed = _time.monotonic() - self._play_start_time

        # ── Pre-scroll: only when the upcoming row is off-screen ─────────────
        # We use rowViewportPosition(row) to test visibility, NOT visualRect().
        # visualRect() can return coordinates that still intersect the viewport
        # rect for rows that are just outside the scrollable area, producing
        # false "visible" results.  rowViewportPosition(row) directly gives
        # the row's y-coordinate in viewport space:
        #   < 0              → row is above the visible area
        #   0 … vp_h-row_h  → row is fully visible
        #   ≥ vp_h           → row is below the visible area (needs scroll)
        future = elapsed + self._PRE_SCROLL_SEC
        vp_h   = self._table.viewport().height()
        follow_row = -1
        while (self._row_transition_index + 1
               < len(self._row_transitions)):
            next_start, _ = self._row_transitions[
                self._row_transition_index + 1]
            if next_start > future:
                break
            self._row_transition_index += 1
        if self._row_transition_index >= 0:
            follow_row = self._row_transitions[
                self._row_transition_index][1]

        # Deriving the target from elapsed time on every tick lets automatic
        # following recover after the user has manually moved the scrollbar.
        if (follow_row > 0
                and _time.monotonic() >= self._manual_scroll_until):
            row_y = self._table.rowViewportPosition(follow_row)
            row_h = self._table.rowHeight(follow_row)
            off_screen = (row_y < 0) or (row_y + row_h > vp_h)
            if off_screen and follow_row != self._last_auto_scroll_row:
                # Near the final rows Qt may be unable to place a row at the
                # requested top edge.  Mark the attempt before calling scrollTo
                # so the 30 ms timer cannot flood the event loop with no-ops.
                self._last_auto_scroll_row = follow_row
                idx = self._table.model().index(follow_row, _HEADER_FIXED_COLS)
                self._table.scrollTo(idx, self._table.ScrollHint.PositionAtTop)

        # ── Highlight: advance the timing cursor to the current cell ─────────
        active = (-1, -1)
        while self._timing_index + 1 < len(self._timing_map):
            if self._timing_map[self._timing_index + 1][0] > elapsed:
                break
            self._timing_index += 1
        if self._timing_index >= 0:
            _, trow, tcol = self._timing_map[self._timing_index]
            active = (trow, tcol)

        if active != self._last_highlighted:
            if self._last_highlighted != (-1, -1):
                pr, pc = self._last_highlighted
                self._set_cell_highlight(pr, pc, highlighted=False)
            if active != (-1, -1):
                r, c = active
                self._set_cell_highlight(r, c, highlighted=True)
                # No scrollTo here – scrolling is handled by the pre-scroll
                # block above so the cell is already in view when we arrive.
            self._last_highlighted = active

    def _set_cell_highlight(self, row: int, col: int, highlighted: bool):
        cell = self._table.cellWidget(row, col)
        if not isinstance(cell, NoteCell):
            return
        if highlighted:
            cell.note_edit.setStyleSheet(
                f"background-color: {_HIGHLIGHT_NOTE_BG.name()}; border: none; font-weight: bold;")
            cell.lyric_edit.setStyleSheet(
                f"background-color: {_HIGHLIGHT_LYRIC_BG.name()}; border: none;")
        else:
            cell.note_edit.setStyleSheet(
                f"background-color: {_NOTE_BG.name()}; border: none;")
            cell.lyric_edit.setStyleSheet(
                f"background-color: {_LYRIC_BG.name()}; border: none;")

    def _clear_all_highlights(self):
        for r in range(1, self._table.rowCount()):
            for ci in range(len(self._col_anga_types)):
                col = _HEADER_FIXED_COLS + ci
                self._set_cell_highlight(r, col, highlighted=False)
        self._last_highlighted = (-1, -1)

    # ── Open CMN Editor ────────────────────────────
    def _open_cmn_editor(self):
        """Launch TutorUI (CMN text editor) as a separate top-level window."""
        try:
            from carnatic.ui.tutor import TutorUI
            if self._cmn_editor is None or not self._cmn_editor.isVisible():
                self._cmn_editor = TutorUI()
                self._cmn_editor.show()
            else:
                self._cmn_editor.raise_()
                self._cmn_editor.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "CMN Editor Error", str(e))

    # ── Keyboard Navigation ─────────────────────────
    def _navigate_cell(self, row: int, col: int, delta: int, field: str):
        """Move focus to the adjacent NoteCell (delta=+1 next, -1 prev).
        Wraps to the previous/next data row at row boundaries.
        SEP separator columns are skipped automatically."""
        total_cols = self._table.columnCount()
        total_rows = self._table.rowCount()
        new_col = col + delta
        while True:
            if new_col < _HEADER_FIXED_COLS:
                row -= 1
                if row < 1:
                    return
                new_col = total_cols - 1
            elif new_col >= total_cols:
                row += 1
                if row >= total_rows:
                    return
                new_col = _HEADER_FIXED_COLS
            cell = self._table.cellWidget(row, new_col)
            if isinstance(cell, NoteCell):
                target = cell.note_edit if field == 'note' else cell.lyric_edit
                target.setFocus()
                return
            new_col += delta   # skip non-NoteCell (SEP) columns

    def _navigate_cell_same_row(self, row: int, col: int, delta: int,
                                field: str = 'note'):
        """Move focus to the next/prev NoteCell, staying in *field* ('note'/'lyric').

        Within the current display row all cells (including those after a SEP
        separator) are visited in column order.  At the row boundary the focus
        wraps to the first/last NoteCell of the next/prev data row.
        """
        total_cols = self._table.columnCount()
        total_rows = self._table.rowCount()
        new_col = col + delta

        # ── Try to find the next/prev NoteCell in the same row ──────────────
        while _HEADER_FIXED_COLS <= new_col < total_cols:
            cell = self._table.cellWidget(row, new_col)
            if isinstance(cell, NoteCell):
                target = cell.note_edit if field == 'note' else cell.lyric_edit
                target.setFocus()
                return
            new_col += delta

        # ── At row boundary: wrap to next / prev data row ───────────────────
        new_row = row + delta
        if new_row < 1 or new_row >= total_rows:
            return   # no more rows in that direction – stay put

        if delta > 0:
            # Moving forward → first NoteCell of next row
            new_col = _HEADER_FIXED_COLS
            while new_col < total_cols:
                cell = self._table.cellWidget(new_row, new_col)
                if isinstance(cell, NoteCell):
                    target = cell.note_edit if field == 'note' else cell.lyric_edit
                    target.setFocus()
                    return
                new_col += 1
        else:
            # Moving backward → last NoteCell of prev row
            new_col = total_cols - 1
            while new_col >= _HEADER_FIXED_COLS:
                cell = self._table.cellWidget(new_row, new_col)
                if isinstance(cell, NoteCell):
                    target = cell.note_edit if field == 'note' else cell.lyric_edit
                    target.setFocus()
                    return
                new_col -= 1

    def _navigate_row(self, row: int, col: int, field: str, delta: int):
        """Move focus up or down one data row, keeping the same column and field."""
        new_row = row + delta
        if new_row < 1 or new_row >= self._table.rowCount():
            return
        cell = self._table.cellWidget(new_row, col)
        if isinstance(cell, NoteCell):
            target = cell.note_edit if field == 'note' else cell.lyric_edit
            target.setFocus()

    # ── Raaga Integration ───────────────────────────
    def _on_raaga_changed(self, raaga_name: str):
        """Called when the Raaga combo text changes. Updates mela, scales, and note map."""
        if not raaga_name.strip():
            self._meta_aarohanam_label.setText("—")
            self._meta_avarohanam_label.setText("—")
            self._meta_mela.setText("")
            self._note_map = {}
            self._aro_note_map = {}
            self._avro_note_map = {}
            self._current_raaga_id = None
            return

        # Try exact match first, then partial
        matches = raaga_module.search_for_raaga_by_name(raaga_name.strip(), is_exact=True)
        if not matches:
            matches = raaga_module.search_for_raaga_by_name(raaga_name.strip(), is_exact=False)
        if not matches:
            return  # No match – keep existing display

        raaga_id, _ = matches[0]
        self._current_raaga_id = raaga_id

        # Melakartha
        mela = raaga_module.get_melakartha(raaga_id)
        self._meta_mela.setText(str(mela))

        # Aarohanam / Avarohanam
        aro = raaga_module.get_aaroganam(raaga_id)
        avro = raaga_module.get_avaroganam(raaga_id)
        self._meta_aarohanam_label.setText("  ".join(aro))
        self._meta_avarohanam_label.setText("  ".join(avro))

        # Build note-resolution map
        self._build_note_map(aro, avro)

    def _build_note_map(self, aro: list, avro: list):
        """Build aarohanam, avarohanam, and combined note maps.

        Each map is  base-letter → raaga-specific variant (e.g. 'R' → 'R2').
        The combined map uses aarohanam variants as the default (aro takes
        priority for notes that appear in both scales).
        """
        def _make_map(notes):
            m = {}
            for note in notes:
                clean = note.replace('^', '').replace("'", '').replace('.', '')
                if not clean:
                    continue
                base = clean[0].upper()
                if base not in m:
                    m[base] = clean
            return m

        self._aro_note_map  = _make_map(aro)
        self._avro_note_map = _make_map(avro)
        # Combined: aarohanam takes priority
        self._note_map = {**self._avro_note_map, **self._aro_note_map}

    # Scale-position order for directional detection (0=lowest, 6=highest in octave)
    _SWARA_ORDER = {'S': 0, 'R': 1, 'G': 2, 'M': 3, 'P': 4, 'D': 5, 'N': 6}
    _RESOLVABLE_SWARA_RE = re.compile(
        r"([.]*)([SRGMPDN])([1-4]?)([\^'.]*)(~[1-4]?)?",
        re.IGNORECASE)

    def _find_predecessor_swara_pos(self, row: int, col: int) -> int:
        """Return the scale position (0–6) of the closest non-empty, non-punctuation
        note that appears *before* the cell at (row, col).  Returns -1 if none found."""
        total_cols = self._table.columnCount()
        scan_row, scan_col = row, col - 1
        while True:
            if scan_col < _HEADER_FIXED_COLS:
                scan_row -= 1
                if scan_row < 1:
                    return -1
                scan_col = total_cols - 1
            cell = self._table.cellWidget(scan_row, scan_col)
            if isinstance(cell, NoteCell):
                note = cell.note().strip()
            elif isinstance(cell, TransitionCell):
                note = cell.transition().strip()
            else:
                note = ''
            if note:
                if note and note not in (',', ';', '-'):
                    matches = list(self._RESOLVABLE_SWARA_RE.finditer(note))
                    if matches:
                        base = matches[-1].group(2).upper()
                        return self._SWARA_ORDER[base]
            scan_col -= 1

    def _resolve_note(self, raw: str,
                      cell_row: int = -1, cell_col: int = -1) -> str:
        """Resolve every generic swara token to its raaga-specific variant.

        Examples: ``R`` -> ``R2``, ``GM`` -> ``G3M1``, and
        ``G M'`` -> ``G3 M1'``. Already-specific tokens pass through unchanged.
        Octave markers, gamakas, spacing, commas, and duration symbols are
        preserved.

        When direction-aware resolution is enabled (checkbox checked), the
        preceding swara, including an earlier token in the same cell, selects
        the aarohanam or avarohanam variant.
        """
        if not raw or not self._note_map:
            return raw
        use_smart = (
            hasattr(self, '_chk_smart_resolve')
            and self._chk_smart_resolve.isChecked()
            and cell_row > 0 and cell_col >= _HEADER_FIXED_COLS
        )
        predecessor_pos = (
            self._find_predecessor_swara_pos(cell_row, cell_col)
            if use_smart else -1)

        def _resolve_token(match):
            nonlocal predecessor_pos
            prefix, base, digit, suffix, gamaka = match.groups()
            base = base.upper()
            curr_pos = self._SWARA_ORDER.get(base.upper(), -1)
            note_map = self._note_map
            if (use_smart and predecessor_pos >= 0 and curr_pos >= 0
                    and (self._aro_note_map or self._avro_note_map)):
                if curr_pos >= predecessor_pos:
                    note_map = self._aro_note_map or self._note_map   # ascending
                else:
                    note_map = self._avro_note_map or self._note_map  # descending
            predecessor_pos = curr_pos
            if digit:
                resolved = base + digit
            else:
                resolved = note_map.get(
                    base, self._note_map.get(base, base))
            return prefix + resolved + suffix + (gamaka or '')

        return self._RESOLVABLE_SWARA_RE.sub(_resolve_token, raw)

    # ── Scale Playback ──────────────────────────────
    def _play_scale(self):
        """Play the Aarohanam + Avarohanam of the selected raaga."""
        if self._current_raaga_id is None:
            QMessageBox.information(self, "No Raaga",
                                    "Please select a Raaga to play its scale.")
            return
        if not self.mplayer:
            QMessageBox.warning(self, "No Player",
                                "No MPlayer instance available.")
            return
        try:
            aro  = raaga_module.get_aaroganam(self._current_raaga_id)
            avro = raaga_module.get_avaroganam(self._current_raaga_id)
            raaga_name = self._meta_ragam.currentText()
            mela  = self._meta_mela.text() or '15'
            tempo = self._meta_tempo.text() or '60'

            # Use TRIPUTA CHATHUSRA (4+2+2 = 8 aksharas) – pad to multiples of 8
            def _to_bars(notes):
                padded = list(notes)
                while len(padded) % 8:
                    padded.append('-')
                bars = []
                for i in range(0, len(padded), 8):
                    c = padded[i:i+8]
                    bars.append(
                        f"{' '.join(c[0:4])} | {' '.join(c[4:6])} | {' '.join(c[6:8])} ||"
                    )
                return '\n'.join(bars)

            cmn_text = (
                f"{{Geetham\n"
                f"#M{mela}\n"
                f"{{Scale: {raaga_name}\n"
                f"{{ Ragam: {raaga_name}\n"
                f"{{ Talam: Triputa (Chathurasra Jathi)\n"
                f"#T4\n"
                f"#J2\n"
                f"#D{tempo}\n"
                f"{{Aarohanam:\n"
                f"{_to_bars(aro)}\n"
                f"{{Avarohanam:\n"
                f"{_to_bars(avro)}\n"
            )

            temp_file = settings._TEMP_PATH + "scale_play.cmn"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(cmn_text)

            scamp_notes, _, solkattu = cparser.parse_notation_file(temp_file)
            temp_midi = settings._TEMP_PATH + "scale_play.mid"
            cmidi.write_to_midifile_from_scamp_notes(
                scamp_notes, temp_midi,
                include_percussion_layer=False,
                solkattu_list=solkattu)

            self._btn_play_scale.setEnabled(False)

            def _bg():
                try:
                    self.mplayer.play_midi_file(temp_midi)
                except Exception as ex:
                    print("Scale playback error:", ex)
                finally:
                    self._btn_play_scale.setEnabled(True)

            threading.Thread(target=_bg, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "Scale Play Error", str(e))


# ──────────────────────────────────────────────────
# Module-level entry point
# ──────────────────────────────────────────────────
def show_ui(language: str = 'en',
            player_type: settings.PLAYER_TYPE = settings.PLAYER_TYPE.SF2_LOADER):
    """
    Launch the Tabular Notation Editor as the main application window.
    The CMN editor (TutorUI) is accessible via the 'Open CMN Editor…' button.
    """
    import sys

    def _except_hook(exc_type, exc_value, exc_tb):
        import traceback
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("TabularEditor exception:\n", tb)

    sys.excepthook = _except_hook
    settings.set_language(language)

    app = QApplication.instance() or QApplication(sys.argv)
    mplayer = cmidi.MPlayer(settings._SOUND_FONT_FILE)
    window = TabularEditorDialog(
        parent=None,
        mplayer=mplayer,
        player_type=player_type,
        include_percussion=True,
    )
    # Make the dialog behave like a top-level window
    window.setWindowFlag(Qt.WindowType.Window, True)
    window.show()
    sys.exit(app.exec())
