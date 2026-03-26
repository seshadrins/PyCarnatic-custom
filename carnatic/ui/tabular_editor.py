"""
Tabular Notation Editor (.ctab)
- Smart grid that auto-adjusts columns for the selected Thaalam & Jaathi
- Each avartam is one table row; each akshara cell has a note + lyric line
- Supports New, Open, Save, Delete row, and Play
"""
import os
import re
import time as _time
import threading
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QWidget, QSizePolicy, QFileDialog,
    QMessageBox, QHeaderView, QAbstractItemView, QFrame,
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

    def keyPressEvent(self, event):
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        editor = self.cell_ref.editor_ref

        if editor is None:
            super().keyPressEvent(event)
            return

        row = self.cell_ref.table_row
        col = self.cell_ref.table_col

        # Tab / Shift-Tab – move between cells
        if key == Qt.Key.Key_Tab:
            if not shift:
                if self.field_type == 'note':
                    self.cell_ref.lyric_edit.setFocus()   # note → lyric same cell
                else:
                    editor._navigate_cell(row, col, +1, 'note')  # lyric → next cell note
            else:
                if self.field_type == 'lyric':
                    self.cell_ref.note_edit.setFocus()    # lyric → note same cell
                else:
                    editor._navigate_cell(row, col, -1, 'lyric') # note → prev cell lyric
            event.accept()
            return

        # Enter/Return – same as Tab forward
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.field_type == 'note':
                self.cell_ref.lyric_edit.setFocus()
            else:
                editor._navigate_cell(row, col, +1, 'note')
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

    def __init__(self, anga_type: str = 'L', parent=None):
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
        self.note_edit.setMaxLength(10)
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
        self.lyric_edit.setMaxLength(20)
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
            resolved = self.editor_ref._resolve_note(raw)
            if resolved != raw:
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
        self._note_map: dict = {}          # base-note → specific variant (e.g. 'R' → 'R2')
        self._current_raaga_id = None      # int raaga index from raaga module
        self._cmn_editor = None            # reference to CMN TutorUI window

        # Playback cell-highlighting support
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setInterval(80)   # ~12 fps polling
        self._highlight_timer.timeout.connect(self._update_highlight)
        self._timing_map: list = []             # [(start_sec, row, col), ...]
        self._play_start_time: float = 0.0
        self._last_highlighted: tuple = (-1, -1)

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
        self._btn_new = QPushButton("New")
        self._btn_open = QPushButton("Open…")
        self._btn_save = QPushButton("Save…")
        self._btn_play = QPushButton("▶ Play")
        self._btn_stop = QPushButton("■ Stop")
        self._btn_cmn = QPushButton("Open CMN Editor…")
        self._btn_close = QPushButton("Close")
        for btn in [self._btn_add, self._btn_del, self._btn_new,
                    self._btn_open, self._btn_save, self._btn_play,
                    self._btn_stop, self._btn_cmn, self._btn_close]:
            btn_bar.addWidget(btn)
        root.addLayout(btn_bar)

        # 5. Table
        self._table = QTableWidget()
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(52)
        root.addWidget(self._table)

        # Connections
        self._btn_add.clicked.connect(self._add_avartam_row)
        self._btn_del.clicked.connect(self._delete_selected_row)
        self._btn_new.clicked.connect(self._new_file)
        self._btn_open.clicked.connect(self._open_file)
        self._btn_save.clicked.connect(self._save_file)
        self._btn_play.clicked.connect(self._play)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_cmn.clicked.connect(self._open_cmn_editor)
        self._btn_close.clicked.connect(self.close)

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

        # Pre-populate from _DEFAULT_META
        self._populate_metadata_panel(ctab_parser._DEFAULT_META)
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
        }

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
        total = sum(s for _, _, s in self._anga_struct)

        # Update anga info label
        parts = [f"{name}({size})" for name, _, size in self._anga_struct]
        self._anga_label.setText(
            "  Structure: " + " | ".join(parts) +
            f"  =  {total} aksharas per avartam")

        # Collect existing grid data before destroying it
        existing = self._collect_grid_rows() if self._table.rowCount() > 1 else []

        # Rebuild table headers
        total_cols = _HEADER_FIXED_COLS + total
        self._table.setColumnCount(total_cols)
        headers = ['Section', 'Speed', 'Bar']

        # Build per-akshara headers
        self._col_anga_types = []   # 'L','D','A' per akshara column
        for full, col_lbl, size in self._anga_struct:
            for i in range(size):
                headers.append(f"{col_lbl}[{i+1}]")
                self._col_anga_types.append(col_lbl[0])  # first char = type

        self._table.setHorizontalHeaderLabels(headers)

        # Color the akshara column headers
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            item = self._table.horizontalHeaderItem(col)
            if item:
                item.setBackground(_ANGA_COLORS.get(atype, _NOTE_BG))

        # Resize fixed cols
        for c in range(_HEADER_FIXED_COLS):
            self._table.setColumnWidth(c, 100 if c == 0 else 60)
        for c in range(_HEADER_FIXED_COLS, total_cols):
            self._table.setColumnWidth(c, 55)

        # Add anga header row (row 0 – read-only labels)
        self._table.setRowCount(1)
        self._table.setRowHeight(0, 22)
        for c in range(_HEADER_FIXED_COLS):
            item = QTableWidgetItem(['Section', 'Speed', 'Bar'][c])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setBackground(QColor(200, 200, 200))
            self._table.setItem(0, c, item)
        col_start = _HEADER_FIXED_COLS
        for full, col_lbl, size in self._anga_struct:
            atype = col_lbl[0]
            color = _ANGA_COLORS.get(atype, _NOTE_BG)
            for i in range(size):
                item = QTableWidgetItem(full if i == 0 else "")
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

        # Re-populate existing rows
        for row_data in existing:
            self._insert_row_from_data(row_data)

    def _add_avartam_row(self):
        """Append an empty avartam row to the table."""
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setRowHeight(r, 52)
        self._init_fixed_cells(r)
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            cell = NoteCell(atype)
            cell.editor_ref = self
            cell.table_row = r
            cell.table_col = col
            self._table.setCellWidget(r, col, cell)

    def _insert_row_from_data(self, note_lyric_pair: dict):
        """Insert a row from saved data {'section','speed','bar','notes','lyrics'}."""
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setRowHeight(r, 52)
        self._init_fixed_cells(r,
                               note_lyric_pair.get('section', ''),
                               note_lyric_pair.get('speed', '1'),
                               note_lyric_pair.get('bar', ''))
        notes = note_lyric_pair.get('notes', [])
        lyrics = note_lyric_pair.get('lyrics', [])
        for ci, atype in enumerate(self._col_anga_types):
            col = _HEADER_FIXED_COLS + ci
            cell = NoteCell(atype)
            cell.editor_ref = self
            cell.table_row = r
            cell.table_col = col
            if ci < len(notes):
                cell.set_note(notes[ci])
            if ci < len(lyrics):
                cell.set_lyric(lyrics[ci])
            self._table.setCellWidget(r, col, cell)

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

    def _delete_selected_row(self):
        rows = sorted(set(i.row() for i in self._table.selectedItems()),
                      reverse=True)
        for r in rows:
            if r > 0:   # never delete the header row
                self._table.removeRow(r)

    # ── Collect Data from Grid ─────────────────────
    def _collect_grid_rows(self) -> list:
        """Return list of dicts from all data rows (skipping row 0 = anga header)."""
        result = []
        for r in range(1, self._table.rowCount()):
            sec_w = self._table.cellWidget(r, 0)
            spd_w = self._table.cellWidget(r, 1)
            bar_i = self._table.item(r, 2)
            section = sec_w.currentText() if sec_w else ''
            speed = spd_w.currentText() if spd_w else '1'
            bar = bar_i.text() if bar_i else str(r)
            notes, lyrics = [], []
            for ci in range(len(self._col_anga_types)):
                cell = self._table.cellWidget(r, _HEADER_FIXED_COLS + ci)
                if isinstance(cell, NoteCell):
                    notes.append(cell.note())
                    lyrics.append(cell.lyric())
                else:
                    notes.append('')
                    lyrics.append('')
            result.append({'section': section, 'speed': speed,
                           'bar': bar, 'notes': notes, 'lyrics': lyrics})
        return result

    def _collect_data(self) -> dict:
        """Build a ctab data dict from the current UI state."""
        data = {'meta': self._read_metadata_from_panel(), 'rows': []}
        for rd in self._collect_grid_rows():
            data['rows'].append({
                'section': rd['section'], 'speed': rd['speed'],
                'bar': rd['bar'], 'row_type': 'N',
                'aksharas': rd['notes'],
            })
            data['rows'].append({
                'section': rd['section'], 'speed': rd['speed'],
                'bar': rd['bar'], 'row_type': 'L',
                'aksharas': rd['lyrics'],
            })
        return data

    def _populate_grid_from_data(self, data: dict):
        """Populate the grid from a loaded ctab data dict."""
        self._populate_metadata_panel(data['meta'])
        self._rebuild_grid()
        # Pair note and lyric rows
        note_map, lyric_map, order = {}, {}, []
        for row in data['rows']:
            key = (row.get('section', ''), row.get('speed', '1'),
                   row.get('bar', '1'))
            if row.get('row_type', 'N') == 'N':
                note_map[key] = row.get('aksharas', [])
                if key not in order:
                    order.append(key)
            else:
                lyric_map[key] = row.get('aksharas', [])
        for key in order:
            sec, spd, bar = key
            self._insert_row_from_data({
                'section': sec, 'speed': spd, 'bar': bar,
                'notes': note_map.get(key, []),
                'lyrics': lyric_map.get(key, []),
            })

    # ── File Operations ────────────────────────────
    def _new_file(self):
        self._filepath = ""
        self._data = ctab_parser.create_empty_data()
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

    # ── Playback ───────────────────────────────────
    def _play(self):
        if not self.mplayer:
            QMessageBox.warning(self, "No Player",
                                "No MPlayer instance available.")
            return
        try:
            data = self._collect_data()
            cmn_text = ctab_parser.convert_to_cmn(data)
            temp_file = settings._TEMP_PATH + "tabular_play.cmn"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(cmn_text)
            # parse_notation_file applies #D, #S, etc. to settings globals
            scamp_notes, _, solkattu = cparser.parse_notation_file(temp_file)
            temp_midi = settings._TEMP_PATH + "tabular_play.mid"
            cmidi.write_to_midifile_from_scamp_notes(
                scamp_notes, temp_midi,
                include_percussion_layer=self.include_percussion,
                solkattu_list=solkattu)
            self.mplayer.is_playing = True
            self._btn_play.setEnabled(False)

            # Build the timing map AFTER parsing (settings.TEMPO is now correct)
            self._timing_map = self._build_timing_map(data)
            self._play_start_time = _time.time()
            self._last_highlighted = (-1, -1)
            self._highlight_timer.start()

            def _bg():
                try:
                    self.mplayer.play_midi_file(temp_midi)
                except Exception as ex:
                    print("Playback error:", ex)
                finally:
                    self.mplayer.is_playing = False
                    self._btn_play.setEnabled(True)

            threading.Thread(target=_bg, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "Play Error", str(e))

    def _stop(self):
        self._highlight_timer.stop()
        self._clear_all_highlights()
        if self.mplayer and self.mplayer.is_playing:
            self.mplayer.stop()
            self.mplayer.is_playing = False
            self._btn_play.setEnabled(True)

    # ── Cell Highlighting ──────────────────────────
    def _build_timing_map(self, data: dict) -> list:
        """Return list of (start_sec, table_row, table_col) for every
        note-start event in the grid (skips , and ; prolongation cells)."""
        try:
            tempo = float(data['meta'].get('Tempo', '60') or '60')
        except ValueError:
            tempo = 60.0
        full_dur = settings._FULL_NOTE_DURATION   # beats per akshara at speed-1

        timing_map = []
        current_time = 0.0

        for grid_row_idx in range(1, self._table.rowCount()):
            spd_w = self._table.cellWidget(grid_row_idx, 1)
            speed = int(spd_w.currentText()) if spd_w else 1
            akshara_sec = full_dur / (2 ** (speed - 1)) * (60.0 / tempo)

            for ci in range(len(self._col_anga_types)):
                col = _HEADER_FIXED_COLS + ci
                cell = self._table.cellWidget(grid_row_idx, col)
                if isinstance(cell, NoteCell):
                    note_text = cell.note().strip()
                    if note_text in (',', ';'):
                        # Prolongation: don't start new timing entry; keep prev highlighted
                        pass
                    else:
                        timing_map.append((current_time, grid_row_idx, col))
                    current_time += akshara_sec
                else:
                    current_time += akshara_sec
        return timing_map

    def _update_highlight(self):
        """Called by QTimer every ~80 ms during playback."""
        if not self.mplayer or not self.mplayer.is_playing:
            self._highlight_timer.stop()
            self._clear_all_highlights()
            self._btn_play.setEnabled(True)
            return

        elapsed = _time.time() - self._play_start_time
        active = (-1, -1)
        for (start, trow, tcol) in self._timing_map:
            if start <= elapsed:
                active = (trow, tcol)
            else:
                break

        if active != self._last_highlighted:
            # Clear old highlight
            if self._last_highlighted != (-1, -1):
                pr, pc = self._last_highlighted
                self._set_cell_highlight(pr, pc, highlighted=False)
            # Apply new highlight
            if active != (-1, -1):
                r, c = active
                self._set_cell_highlight(r, c, highlighted=True)
                self._table.scrollTo(self._table.model().index(r, c))
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
        """Move focus to the adjacent akshara cell (delta=+1 next, -1 prev).
        Wraps to the previous/next data row at row boundaries."""
        new_col = col + delta
        total_cols = self._table.columnCount()
        total_rows = self._table.rowCount()

        if new_col < _HEADER_FIXED_COLS:
            # Wrap to previous data row, last akshara
            new_row = row - 1
            if new_row < 1:
                return  # already at very start
            new_col = total_cols - 1
            row = new_row
        elif new_col >= total_cols:
            # Wrap to next data row, first akshara
            new_row = row + 1
            if new_row >= total_rows:
                return  # at end – don't auto-add; user can press + Add Avartam
            new_col = _HEADER_FIXED_COLS
            row = new_row

        cell = self._table.cellWidget(row, new_col)
        if isinstance(cell, NoteCell):
            target = cell.note_edit if field == 'note' else cell.lyric_edit
            target.setFocus()

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
        """Build mapping from generic swara letter → raaga-specific variant.
        E.g. 'R' → 'R2' for Kalyani, 'M' → 'M2' for Kalyani."""
        self._note_map = {}
        # Process avarohanam first, then aarohanam (aarohanam takes priority for ambiguous notes)
        for note in (avro + aro):
            # Strip octave markers (^, ', .)
            clean = note.replace('^', '').replace("'", '').replace('.', '')
            if not clean:
                continue
            base = clean[0].upper()   # 'S', 'R', 'G', 'M', 'P', 'D', 'N'
            if base not in self._note_map:
                self._note_map[base] = clean  # e.g. 'R' → 'R2'

    def _resolve_note(self, raw: str) -> str:
        """Resolve a generic swara to its raaga-specific variant, preserving octave markers.
        Examples: 'R' -> 'R2', "R'" -> "R2'", '.R' -> '.R2'.
        Already-specific notes (e.g. 'R2') pass through unchanged."""
        if not raw or not self._note_map:
            return raw
        # Match: optional leading dots (lower octave), bare letter (no digit follows),
        # then optional octave suffix (^ or ' or .)
        m = re.match(r"^([.]*)(S|R|G|M|P|D|N)([\^'.]*)$", raw.strip(), re.IGNORECASE)
        if not m:
            return raw  # already specific (e.g. 'R2') or non-note ('-', '=', '.')
        prefix, base, suffix = m.groups()
        resolved = self._note_map.get(base.upper(), base.upper())
        return prefix + resolved + suffix

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

