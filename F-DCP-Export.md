# Delete, Copy, Paste, and Spreadsheet Export

## Status

Implemented in the Tabular Notation Editor.

## Row selection

- Clicking selects one whole display row.
- `Ctrl+Click` selects separate rows.
- `Shift+Click` selects a range.
- The anga header row is excluded from row operations.

## Delete Row(s)

Use **Delete Row(s)** or press `Delete` while the table has focus.

- One or more selected rows are removed together.
- Deletion runs from the bottom upward so non-contiguous selections are safe.
- Rows following each deletion move upward.
- Internal cell navigation references are refreshed.
- Bars are renumbered.
- The row occupying the first deleted position is selected, or the new final
  row is selected when the old final row was deleted.

## Copy Row(s)

Use **Copy Row(s)** or press `Ctrl+C` while the table has focus.

The internal row clipboard stores an independent snapshot of each selected row,
in visual order, including:

- Section
- Speed
- Notes
- Transition swaras
- Lyrics

The displayed Bar number is not copied because Bars are derived from position.
Normal `Ctrl+C` continues to work inside an actively edited text field.

The row clipboard belongs to the open editor. It is not copied to the Windows
clipboard for use in other applications.

## Paste Row(s)

Use **Paste Row(s)** or press `Ctrl+V` while the table has focus.

- When rows are selected, copied rows are inserted immediately after the last
  selected row.
- With no selected row, copied rows are appended.
- Existing rows at and below the insertion point move downward; Paste never
  overwrites them.
- Pasted rows retain their copied Section, Speed, notes, transitions, and
  lyrics.
- Pasted rows are selected after insertion.
- Bars and internal navigation references are refreshed.
- Repeated Paste operations create independent copies.

Paste is rejected with a message if the copied row shape does not match the
current Thaalam, Jaathi, or **Avartams Per Line** grid.

## Bar numbering

Bars are recalculated after Add, Delete, Paste, load, CSV import, and grid
rebuild operations.

With **Avartams Per Line = 1**, displayed Bars are:

`1, 2, 3, 4, ...`

With **Avartams Per Line = N**, each display row shows its first avartam:

`1, 1 + N, 1 + 2N, 1 + 3N, ...`

For two avartams per line, this is:

`1, 3, 5, 7, ...`

CTAB saving continues to expand display rows into individual avartams numbered
sequentially as `1, 2, 3, 4, ...`.

## Multi-swara raaga resolution

When focus leaves a note or transition cell, every generic swara token in that
cell is resolved using the selected raaga. This works for concatenated and
space-separated swaras:

- `GM` becomes `G3M1` when the raaga maps Ga to `G3` and Ma to `M1`.
- `G M'` becomes `G3 M1'`.
- Already resolved tokens such as `G3` remain unchanged.
- Octave markers, gamakas, commas, semicolons, hyphens, and spacing are
  preserved.

When smart directional resolution is enabled, each token also becomes the
predecessor used to resolve the next token in the same cell. Cell length limits
expand when necessary so adding variant numbers cannot truncate the result.

## Spreadsheet export cleaning

The **Export** command offers two formats:

- **Excel Workbook (`.xlsx`)**: Notes and Lyrics are placed on separate
  worksheet tabs. The `Notes` sheet is always present. The `Lyrics` sheet is
  created only when at least one lyric value is present.
- **CSV (`.csv`)**: Retains the single-table, Excel-compatible CSV layout
  because CSV files cannot contain worksheet tabs.

Export cleans temporary note and transition values; it does not modify the
editor cells, playback notation, or saved CTAB data.

Note (`N`) columns are always exported. Each transition (`T`) or lyric (`L`)
column is exported only when that specific column contains at least one
non-blank value in the composition. For example, `Av1_T1` and `Av1_L1` are
omitted when all their values are blank. A value in any row keeps the
corresponding column and blank values in its other rows remain blank.

For every swara token in every exported note and transition cell:

- Swara variant numbers are removed: `R2` becomes `R`, `G3` becomes `G`, etc.
- The gamaka marker `~` is removed.
- An optional gamaka-neighbour number following `~` is removed.
- Octave markers `.` and `'` are preserved.
- Spaces, note separators, `,`, and `;` are preserved.
- Every swara in concatenated and space-separated multi-swara cells is cleaned.
- Lyrics, Section, Speed, and Bar values are not cleaned.

Examples:

| Editor value | Exported value |
|---|---|
| `R2` | `R` |
| `M1'` | `M'` |
| `D2~` | `D` |
| `G3~2` | `G` |
| `R2 G3 M1'` | `R G M'` |
| `R2G3'M1~2` | `RG'M` |
| `.N2, S;` | `.N, S;` |

## Acceptance coverage

The implementation has automated regression coverage for:

- Copying and pasting multiple selected rows.
- Insertion order and pushing following rows downward.
- Deleting multiple non-contiguous rows and pulling following rows upward.
- Bar renumbering.
- Selection of pasted rows.
- Button-equivalent keyboard shortcuts.
- All documented single- and multi-swara export-cleaning examples.
- Optional CSV and XLSX export formats.
- Separate Notes and Lyrics workbook tabs.
- Omission of the Lyrics tab when no lyrics are present.
