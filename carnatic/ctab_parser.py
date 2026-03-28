"""
Module for Tabular Notation Format (.ctab)
- Defines anga structure helpers
- Reads/writes .ctab CSV files
- Converts .ctab data to .cmn notation string for playback
- Converts .cmn notation files to .ctab data (best-effort)
"""
import csv
import os
import re as _re
from carnatic import settings

_CTAB_SEPARATOR = "---"
_CTAB_EXTENSION = ".ctab"

# Anga type sequence (L=Laghu, D=Drutam, A=Anudrutam) per thaala index 1-7
_THAALA_ANGA_SEQUENCES = {
    1: ['L'],              # EKA
    2: ['D', 'L'],         # ROOPAKA
    3: ['L', 'A', 'D'],    # JAMPA
    4: ['L', 'D', 'D'],    # THRIPUTAI
    5: ['L', 'D', 'L'],    # MATHYA
    6: ['L', 'L', 'D', 'D'],   # ATA
    7: ['L', 'D', 'L', 'L'],   # DHURVA
}

_ANGA_FULL_NAMES = {'L': 'Laghu', 'D': 'Drutam', 'A': 'Anudrutam'}
_DRUTAM_AKSHARAS = 2
_ANUDRUTAM_AKSHARAS = 1

SECTION_NAMES = ['Pallavi', 'Anupallavi', 'Muktayi Swaram',
                 'Charanam 1', 'Charanam 2', 'Charanam 3', 'Charanam 4',
                 'Ettugada Swaram', 'Other']
SPEED_NAMES = ['1', '2', '3']
COMPOSITION_TYPES = ['Geetham', 'Varnam', 'Kriti', 'Swarajaathi',
                     'Thillana', 'Ashtapadi', 'Other']
LANGUAGES = ['Sanskrit', 'Tamil', 'Telugu', 'Kannada',
             'Malayalam', 'Hindi', 'Other']

_DEFAULT_META = {
    'Type': 'Geetham', 'Title': '', 'Ragam': '', 'Melakartha': '15',
    'Thaalam': 'THRIPUTAI', 'Jaathi': 'CHATHUSRA',
    'Tempo': '60', 'Composer': '', 'Language': 'Sanskrit', 'Description': '',
}


def get_anga_structure(thaala_index: int, jaathi_index: int) -> list:
    """
    Returns list of (full_name, col_label, num_aksharas) for each anga.
    col_label uses notation like 'L1', 'D1', 'D2', 'A1'.
    """
    sequence = _THAALA_ANGA_SEQUENCES.get(thaala_index, ['L'])
    jaathi_aksharas = settings.jaathi_no[jaathi_index]
    result = []
    counts = {'L': 0, 'D': 0, 'A': 0}
    for anga_type in sequence:
        counts[anga_type] += 1
        size = (jaathi_aksharas if anga_type == 'L'
                else _DRUTAM_AKSHARAS if anga_type == 'D'
                else _ANUDRUTAM_AKSHARAS)
        result.append((_ANGA_FULL_NAMES[anga_type],
                        f"{anga_type}{counts[anga_type]}",
                        size))
    return result


def get_total_aksharas(thaala_index: int, jaathi_index: int) -> int:
    return sum(s for _, _, s in get_anga_structure(thaala_index, jaathi_index))


def create_empty_data() -> dict:
    return {'meta': dict(_DEFAULT_META), 'rows': []}


def get_thaala_index(name: str) -> int:
    try:
        return settings.THAALA_NAMES[name.upper()].value
    except KeyError:
        return int(settings.THAALA_INDEX)


def get_jaathi_index(name: str) -> int:
    try:
        return settings.JAATHI_NAMES[name.upper()].value
    except KeyError:
        return int(settings.JAATHI_INDEX)


def read_ctab(filepath: str) -> dict:
    """Read a .ctab file and return a data dict."""
    data = create_empty_data()
    with open(filepath, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        in_notation = False
        headers_read = False
        for row in reader:
            if not row:
                continue
            if row[0].strip() == _CTAB_SEPARATOR:
                in_notation = True
                continue
            if not in_notation:
                if len(row) >= 2:
                    key, val = row[0].strip(), row[1].strip()
                    if key in data['meta']:
                        data['meta'][key] = val
            else:
                if not headers_read:
                    headers_read = True  # skip header row
                    continue
                if len(row) < 4:
                    continue
                data['rows'].append({
                    'section': row[0].strip(),
                    'speed': row[1].strip(),
                    'bar': row[2].strip(),
                    'row_type': row[3].strip(),
                    'aksharas': [c.strip() for c in row[4:]],
                })
    return data


def write_ctab(data: dict, filepath: str):
    """Write a .ctab file from data dict."""
    meta = data['meta']
    ti = get_thaala_index(meta.get('Thaalam', 'THRIPUTAI'))
    ji = get_jaathi_index(meta.get('Jaathi', 'CHATHUSRA'))
    total = get_total_aksharas(ti, ji)
    headers = [f"A{i+1}" for i in range(total)]
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for key, val in meta.items():
            writer.writerow([key, val])
        writer.writerow([_CTAB_SEPARATOR])
        writer.writerow(['Section', 'Speed', 'Bar', 'RowType'] + headers)
        for row in data['rows']:
            ak = list(row.get('aksharas', []))
            while len(ak) < total:
                ak.append('')
            writer.writerow([row.get('section', ''), row.get('speed', '1'),
                             row.get('bar', '1'), row.get('row_type', 'N')] + ak[:total])


def convert_to_cmn(data: dict) -> str:
    """Convert ctab data dict to .cmn notation string."""
    meta = data['meta']
    ti = get_thaala_index(meta.get('Thaalam', 'THRIPUTAI'))
    ji = get_jaathi_index(meta.get('Jaathi', 'CHATHUSRA'))
    anga_struct = get_anga_structure(ti, ji)

    lines = []
    lines.append(f"{{ {meta.get('Type', 'Geetham')}")
    lines.append(f"#M{meta.get('Melakartha', '15')}")
    lines.append(f"{{ {meta.get('Title', '')}")
    lines.append(f"{{ Ragam: {meta.get('Ragam', '')}")
    lines.append(f"{{ Talam: {meta.get('Thaalam', '')} ({meta.get('Jaathi', '')} Jathi)")
    lines.append(f"#T{ti}")
    lines.append(f"#J{ji}")
    tempo = meta.get('Tempo', '60')
    if tempo:
        lines.append(f"#D{tempo}")
    lines.append(f"{{ Composer: {meta.get('Composer', '')}")
    if meta.get('Description', ''):
        lines.append(f"{{ {meta.get('Description', '')}")
    lines.append("")

    # Pair note rows with lyric rows using (section, speed, bar) as key
    note_rows, lyric_rows, order = {}, {}, []
    for row in data['rows']:
        key = (row.get('section', ''), row.get('speed', '1'), row.get('bar', '1'))
        if row.get('row_type', 'N') == 'N':
            note_rows[key] = row
            if key not in order:
                order.append(key)
        else:
            lyric_rows[key] = row

    prev_section, prev_speed = None, None
    for key in order:
        section, speed, bar = key
        if section != prev_section:
            lines.append(f"{{ {section}:")
            prev_section = section
        speed_val = int(speed) if speed.isdigit() else 1
        if speed_val != prev_speed:
            lines.append(f"#S{speed_val}")
            prev_speed = speed_val

        note_row = note_rows.get(key)
        lyric_row = lyric_rows.get(key)

        def _build_line(aksharas):
            parts = []
            idx = 0
            for _, _, size in anga_struct:
                group = []
                for _ in range(size):
                    cell = aksharas[idx].strip() if idx < len(aksharas) else ''
                    group.append(cell if cell else '-')
                    idx += 1
                parts.append(' '.join(group))
            return ' | '.join(parts) + ' ||'

        if note_row:
            lines.append(_build_line(note_row.get('aksharas', [])))
        if lyric_row:
            lyric_line = _build_line(lyric_row.get('aksharas', []))
            lines.append('{ ' + lyric_line)

    return '\n'.join(lines)


# ── CMN → CTAB converter ──────────────────────────────────────────────────────

# Matches a CMN command line: #T4, #J2, #M15, #S1, #D60 …
_CMD_RE = _re.compile(r'^\s*#([DIJMNPST])(\d+)')

# Matches individual note tokens in a CMN notation line.
# Handles: S, R2, G3, M2', D., N^, S', etc.; also , and ;
_CMN_NOTE_RE = _re.compile(
    r'([SsRrGgMmPpDdNn][1-4]?[\.\'\^]?|[,;])'
)

# Known section keywords (lowercase) → canonical CTAB section name
_SECTION_MAP = [
    ('pallavi',        'Pallavi'),
    ('anupallavi',     'Anupallavi'),
    ('charanam 4',     'Charanam 4'),
    ('charanam 3',     'Charanam 3'),
    ('charanam 2',     'Charanam 2'),
    ('charanam 1',     'Charanam 1'),
    ('charanam',       'Charanam 1'),
    ('muktayi',        'Muktayi Swaram'),
    ('ettugada',       'Ettugada Swaram'),
]

# Comment keywords that are NOT song titles
_NON_TITLE_KEYWORDS = (
    'ragam', 'raagam', 'talam', 'thaalam', 'composer', 'meaning',
    'pallavi', 'charanam', 'anupallavi', 'arog', 'avarog',
    'geetham', 'varnam', 'kriti', 'taal', 'swaram', 'ettugada',
)


def _split_tokens_into_avartams(tokens: list, total_aks: int) -> list:
    """Split note tokens into avartam-sized chunks.

    ';' counts as 2 akshara positions (it extends the previous note by 2x
    duration in the CMN player).  All other tokens count as 1 position.
    """
    if not tokens or total_aks <= 0:
        return [list(tokens)] if tokens else [[]]

    chunks: list = []
    chunk: list = []
    pos = 0
    for tok in tokens:
        chunk.append(tok)
        pos += 2 if tok.strip() == ';' else 1
        if pos >= total_aks:
            chunks.append(chunk)
            chunk = []
            pos = 0
    if chunk:
        chunks.append(chunk)
    return chunks if chunks else [[]]


def convert_cmn_to_ctab(cmn_filepath: str) -> dict:
    """Best-effort conversion of a .cmn file to ctab data dict.

    The function parses #T/#J/#M/#D/#S commands for musical settings,
    extracts metadata from { comment lines, and groups note tokens from
    notation lines (those containing ||) into avartam-sized CTAB rows.

    Lyric lines (comment lines that contain ||) are paired with the
    immediately preceding notation line.
    """
    data = create_empty_data()
    meta = data['meta']

    # Working state
    thaala_idx = int(settings.THAALA_NAMES.THRIPUTAI)
    jaathi_idx = int(settings.JAATHI_NAMES.CHATHUSRA)
    current_speed = 1
    current_section = 'Pallavi'
    bar_counter = 1
    title_candidates: list = []
    rows: list = []          # accumulated {section, speed, bar, notes, lyrics}
    pending: dict | None = None   # last notation block waiting for lyrics

    with open(cmn_filepath, 'r', encoding='utf-8', errors='replace') as fh:
        file_lines = fh.readlines()

    for raw_line in file_lines:
        line = raw_line.strip()
        if not line:
            continue

        # ── Command line ──────────────────────────────
        m = _CMD_RE.match(line)
        if m:
            key, val = m.group(1), int(m.group(2))
            if key == 'T':
                thaala_idx = val
            elif key == 'J':
                jaathi_idx = val
            elif key == 'M':
                meta['Melakartha'] = str(val)
            elif key == 'D':
                meta['Tempo'] = str(val)
            elif key == 'S':
                # Flush pending before speed change
                if pending is not None:
                    rows.append(pending)
                    pending = None
                current_speed = val
            continue

        # ── Comment / lyric line ─────────────────────
        if line.startswith('{'):
            text = line[1:].strip()
            low = text.lower()

            # Lyric line – comment that contains || notation markers
            if '||' in text:
                lyric_tokens = [
                    t for t in _re.split(r'\s+',
                        _re.sub(r'\|\|?', ' ', text)) if t
                ]
                if pending is not None:
                    pending['lyrics'] = lyric_tokens
                    rows.append(pending)
                    pending = None
                continue

            # Section detection (flush pending before new section)
            for key_phrase, sec_name in _SECTION_MAP:
                if key_phrase in low:
                    if pending is not None:
                        rows.append(pending)
                        pending = None
                    current_section = sec_name
                    bar_counter = 1
                    break

            # Metadata extraction
            if low.startswith('ragam:') or low.startswith('raagam:'):
                meta['Ragam'] = text.split(':', 1)[1].strip()
            elif low.startswith('composer:'):
                meta['Composer'] = text.split(':', 1)[1].strip()

            # Title candidate: first substantial comment without known keywords
            if (text and not meta.get('Title')
                    and not any(k in low for k in _NON_TITLE_KEYWORDS)):
                # Also skip type keywords embedded in the first line
                is_type_line = any(
                    ct.lower() in low for ct in COMPOSITION_TYPES)
                if not is_type_line:
                    title_candidates.append(text)
            continue

        # ── Notation line ─────────────────────────────
        if '||' in line:
            if pending is not None:
                rows.append(pending)
                pending = None

            note_tokens = _CMN_NOTE_RE.findall(
                line.replace('||', ' ').replace('|', ' '))

            total_aks = get_total_aksharas(thaala_idx, jaathi_idx)
            avartam_chunks = _split_tokens_into_avartams(note_tokens, total_aks)

            for i, chunk in enumerate(avartam_chunks):
                row_data = {
                    'section': current_section,
                    'speed':   str(current_speed),
                    'bar':     str(bar_counter),
                    'notes':   chunk,
                    'lyrics':  [],
                }
                bar_counter += 1
                if i < len(avartam_chunks) - 1:
                    rows.append(row_data)     # intermediate – no lyrics
                else:
                    pending = row_data        # last chunk waits for lyric line

    # Flush any remaining pending row
    if pending is not None:
        rows.append(pending)

    # Set title from candidates
    if title_candidates and not meta.get('Title'):
        meta['Title'] = title_candidates[0]

    # Resolve thaala/jaathi names from their index values
    for t in settings.THAALA_NAMES:
        if t.value == thaala_idx:
            meta['Thaalam'] = t.name
            break
    for j in settings.JAATHI_NAMES:
        if j.value == jaathi_idx:
            meta['Jaathi'] = j.name
            break

    # Build CTAB rows
    total_aks = get_total_aksharas(thaala_idx, jaathi_idx)
    for row in rows:
        notes  = (row.get('notes',  []) + [''] * total_aks)[:total_aks]
        lyrics = (row.get('lyrics', []) + [''] * total_aks)[:total_aks]

        data['rows'].append({
            'section':  row['section'],
            'speed':    row['speed'],
            'bar':      row['bar'],
            'row_type': 'N',
            'aksharas': notes,
        })
        if any(lyr.strip() for lyr in lyrics):
            data['rows'].append({
                'section':  row['section'],
                'speed':    row['speed'],
                'bar':      row['bar'],
                'row_type': 'L',
                'aksharas': lyrics,
            })

    return data
