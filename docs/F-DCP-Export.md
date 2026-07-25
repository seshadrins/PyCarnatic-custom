# Feature Design: Delete, Copy, Paste, and Clean Spreadsheet Export

## Status

This document describes the proposed functionality for review. It does not
implement the functionality.

## Scope

The Tabular Notation Editor will support:

1. Deleting one or more selected display rows.
2. Copying one or more selected display rows.
3. Pasting copied rows as newly inserted rows.
4. Automatically renumbering the **Bar** column after a structural change.
5. Removing swara variant numbers and gamaka notation from swaras during
   spreadsheet export.

The editor data and saved CTAB file will retain the original swara numbers and
gamaka notation. Cleaning applies only to exported spreadsheet data.

## Terminology

- **Display row**: One visible editable row in the table.
- **Avartam**: One rhythmic cycle. A display row can contain one or more
  avartams, depending on the **Avartams Per Line** setting.
- **Selected rows**: All data rows selected in the table. The anga header row
  is never included.
- **Row payload**: Section, Speed, notes, transition swaras, and lyrics for a
  display row. The displayed Bar value is not copied as permanent data because
  it is recalculated from row position.

## User Interface

Add the following controls beside the existing row controls:

- **Copy Row(s)**
- **Paste Row(s)**
- Keep the existing **Delete Row** control, but make its label plural-aware or
  rename it to **Delete Row(s)**.

Keyboard shortcuts:

- `Ctrl+C`: Copy selected row or rows.
- `Ctrl+V`: Paste copied row or rows.
- `Delete`: Delete selected row or rows when focus is on the table.

The shortcuts operate on whole display rows, not individual cell text. Normal
text editing shortcuts continue to work while the cursor is actively editing a
note, transition, lyric, or metadata text field.

## Selecting One or More Rows

The table remains in whole-row selection mode.

- Clicking a row selects one row.
- `Ctrl+Click` selects or deselects separate rows.
- `Shift+Click` selects a continuous range.
- Operations use selected data rows in ascending visual order.
- The header row cannot be copied, pasted over, or deleted.

## Delete Row(s)

### Behavior

1. Read all selected data-row indexes.
2. If no data row is selected, do nothing.
3. Delete selected rows from bottom to top so earlier row indexes remain valid.
4. Rows below the deleted rows move upward automatically.
5. Refresh every editable cell's internal row and column reference.
6. Renumber all Bars from top to bottom.
7. Select a sensible remaining row:
   - Prefer the row now occupying the first deleted position.
   - If deletion removed the last row, select the new last row.
   - If no data rows remain, leave the table with only its header.

### Example

Before deleting Bars 2 and 3:

| Table position | Bar |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 3 |
| 4 | 4 |
| 5 | 5 |

After deletion:

| Table position | Bar |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 3 |

The former Bars 4 and 5 have moved upward and become Bars 2 and 3.

## Copy Row(s)

### Behavior

1. Collect each selected row in top-to-bottom order.
2. Copy the complete row payload:
   - Section
   - Speed
   - All note values
   - All transition-swara values
   - All lyrics
3. Store an independent snapshot so later edits to the source rows do not
   modify the copied values.
4. Do not treat the current displayed Bar number as copied content.
5. Copying does not alter the table.

The first implementation will use an editor-level row clipboard. It is intended
for copying rows within the same open Tabular Notation Editor. It will not place
the CTAB structure onto the Windows clipboard for use in unrelated programs.

If **Avartams Per Line**, Thaalam, or Jaathi changes after copying, Paste will be
disabled or rejected with a clear message when the copied row shape no longer
matches the current grid. This prevents silent loss or misalignment of notes.

## Paste Row(s)

### Insertion Position

- If one or more data rows are selected, insert the copied rows immediately
  **after the last selected row**.
- If no data row is selected, append the copied rows at the bottom.

This matches the current **Add Avartam** insertion convention.

### Behavior

1. Validate that copied data exists and matches the current grid structure.
2. Determine the insertion position.
3. Insert enough new display rows for the copied payload.
4. Populate the inserted rows in their original copied order.
5. Existing rows at and below the insertion position move downward; no existing
   row is overwritten.
6. Refresh all cell references.
7. Renumber all Bars.
8. Select the newly pasted rows.

Repeated Paste operations create additional independent copies.

### Example

Copy Bars 2 and 3, select Bar 4, then Paste:

| Resulting row | Content source | New Bar |
|---:|---|---:|
| 1 | Original Bar 1 | 1 |
| 2 | Original Bar 2 | 2 |
| 3 | Original Bar 3 | 3 |
| 4 | Original Bar 4 | 4 |
| 5 | Copy of original Bar 2 | 5 |
| 6 | Copy of original Bar 3 | 6 |
| 7 | Original Bar 5 | 7 |

The following rows are pushed downward rather than replaced.

## Bar Renumbering

Bar numbers become position-derived and read-only in practice. Renumbering runs
after Add, Delete, Paste, file load, CSV import, and any grid rebuild that can
change row positions.

When **Avartams Per Line = 1**, displayed Bar values are:

`1, 2, 3, 4, ...`

When **Avartams Per Line = N**, each display row shows the number of its first
avartam:

`1, 1 + N, 1 + 2N, 1 + 3N, ...`

For example, with two avartams per line, Bars are:

`1, 3, 5, 7, ...`

When saved to CTAB, the existing save logic continues to expand display rows
into individual avartams and assigns sequential CTAB Bars:

`1, 2, 3, 4, ...`

## Spreadsheet Export Cleaning

### Current Export Format

The existing **Export CSV** command creates a UTF-8 CSV file that opens in
Microsoft Excel. This design applies the cleaning to that export path. It does
not introduce a native `.xlsx` file unless that is requested separately.

### Cleaning Rules

Cleaning applies to every exported note swara and transition swara. It does not
change Section, Speed, Bar, or lyric values.

For each swara token:

1. Remove its swara variant number:
   - `R1`, `R2`, `R3`, `R4` become `R`
   - `G1` through `G4` become `G`
   - `M1` through `M4` become `M`
   - `D1` through `D4` become `D`
   - `N1` through `N4` become `N`
2. Remove gamaka notation:
   - Remove `~`.
   - Remove an optional gamaka-neighbour number following `~`.
3. Preserve the swara letter.
4. Preserve octave markers (`.` and `'`).
5. Preserve note separators and spacing already present in the cell.
6. Apply the rules to every token in a cell, including concatenated or
   space-separated multiple swaras.
7. Preserve duration/control symbols such as `,` and `;`.

Cleaning must be token-aware. It must not remove unrelated digits from lyrics,
Bar numbers, metadata, or other non-swara text.

### Examples

| Editor value | Exported value | Explanation |
|---|---|---|
| `R2` | `R` | Swara variant removed |
| `M1'` | `M'` | Variant removed; upper-octave marker kept |
| `D2~` | `D` | Variant and gamaka marker removed |
| `G3~2` | `G` | Variant, `~`, and gamaka-neighbour number removed |
| `R2 G3 M1'` | `R G M'` | Every swara in a spaced multi-swara cell cleaned |
| `R2G3'M1~2` | `RG'M` | Every swara in a concatenated cell cleaned |
| `.N2, S;` | `.N, S;` | Lower-octave and duration symbols preserved |
| `S` | `S` | No change needed |

### Export Safety

Export cleaning operates on temporary output values. It must not:

- Rewrite cells in the editor.
- Change playback notation.
- Change saved CTAB content.
- Change imported data.
- Remove swara numbers or gamakas from lyrics.

## Proposed Internal Structure

The implementation should add small, testable helpers:

- `_selected_data_rows()`  
  Returns unique selected data-row indexes in ascending order using the table's
  selection model.

- `_renumber_bars()`  
  Recalculates the displayed starting Bar for every display row.

- `_copy_selected_rows()`  
  Stores deep copies of selected row payloads plus grid-shape information.

- `_paste_copied_rows()`  
  Inserts copied payloads after the last selected row or at the end.

- `_clean_swara_for_export(value)`  
  Removes swara variant numbers and gamaka notation from every swara token in a
  cell without changing non-swara data.

The existing row-data representation returned by `_collect_grid_rows()` can be
reused for copy and paste.

## Acceptance Criteria

1. One selected row can be deleted.
2. Multiple contiguous or non-contiguous selected rows can be deleted together.
3. Rows below deleted rows move upward.
4. One or more selected rows can be copied and pasted.
5. Paste inserts rows and pushes existing following rows downward.
6. Copied rows retain Section, Speed, notes, transitions, and lyrics.
7. Delete, Add, and Paste leave all internal cell row references correct.
8. Bars are correctly renumbered after every structural operation.
9. Bar numbering respects **Avartams Per Line**.
10. CSV export removes swara variant numbers from every swara in every note and
    transition cell.
11. CSV export removes gamaka notation from every swara.
12. Multiple swaras within one cell are all cleaned.
13. Octave markers, separators, duration symbols, and lyrics are preserved.
14. Export does not modify the editor or CTAB source data.

## Review Decisions

Please confirm or change these points before implementation:

1. Paste inserts **after the last selected row**; with no selection it appends.
2. Copy/Paste initially uses an internal row clipboard, not the Windows
   clipboard.
3. Export remains Excel-compatible CSV rather than adding native `.xlsx`.
4. Octave markers (`.` and `'`) remain in exported swaras.
5. Transition-swara columns remain in the export, but their swaras are cleaned
   using the same rules as normal note cells.
