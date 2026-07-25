"""
Module for Tabular Notation Format (.ctab)
- Defines anga structure helpers
- Reads/writes .ctab files (pipe-delimited, backward-compatible with comma CSV)
- Converts .ctab data to .cmn notation string for playback
- Converts .cmn notation files to .ctab data (best-effort, raaga-aware)
"""
import csv
import io
import os
import re as _re
from carnatic import settings
from carnatic import raaga as _raaga_module

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
SPEED_NAMES = ['0.5', '1', '1.5', '2', '2.5', '3']
COMPOSITION_TYPES = ['Geetham', 'Varnam', 'Kriti', 'Swarajaathi',
                     'Thillana', 'Ashtapadi', 'Other']
LANGUAGES = ['Sanskrit', 'Tamil', 'Telugu', 'Kannada',
             'Malayalam', 'Hindi', 'Other']

_DEFAULT_META = {
    'Type': 'Geetham', 'Title': '', 'Ragam': '', 'Melakartha': '15',
    'Thaalam': 'THRIPUTAI', 'Jaathi': 'CHATHUSRA',
    'Tempo': '60', 'Composer': '', 'Language': 'Sanskrit', 'Description': '',
    'AvartamsPerLine': '1',
    'ShowTransitions': 'False', 'MaxCharsPerCell': '8',
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
    """Read a .ctab file and return a data dict.

    Supports both the new pipe-delimited format (|) and the legacy
    comma-delimited CSV format.  Detection is automatic: if any line in the
    file contains a pipe character the pipe format is used; otherwise the
    file is parsed as CSV (which handles quoted commas like "","" in aksharas).
    """
    data = create_empty_data()
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        raw_lines = f.readlines()

    # Detect delimiter by inspecting the raw text
    use_pipe = any('|' in line for line in raw_lines)

    def _split(line: str) -> list:
        if use_pipe:
            return [c.strip() for c in line.rstrip('\n').rstrip('\r').split('|')]
        # Fall back to csv.reader to handle quoted commas correctly
        return next(csv.reader(io.StringIO(line.rstrip('\n'))))

    in_notation = False
    headers_read = False
    for raw_line in raw_lines:
        if not raw_line.strip():
            continue
        row = _split(raw_line)
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
                headers_read = True  # skip column-header row
                continue
            if len(row) < 4:
                continue
            data['rows'].append({
                'section':  row[0].strip(),
                'speed':    row[1].strip(),
                'bar':      row[2].strip(),
                'row_type': row[3].strip(),
                'aksharas': [c.strip() for c in row[4:]],
            })
    return data


def write_ctab(data: dict, filepath: str):
    """Write a .ctab file from data dict using | as delimiter."""
    meta = data['meta']
    ti = get_thaala_index(meta.get('Thaalam', 'THRIPUTAI'))
    ji = get_jaathi_index(meta.get('Jaathi', 'CHATHUSRA'))
    total = get_total_aksharas(ti, ji)
    headers = [f"A{i+1}" for i in range(total)]

    def _write_row(cells, fh):
        fh.write('|'.join(str(c) for c in cells) + '\n')

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        for key, val in meta.items():
            _write_row([key, val], f)
        _write_row([_CTAB_SEPARATOR], f)
        _write_row(['Section', 'Speed', 'Bar', 'RowType'] + headers, f)
        for row in data['rows']:
            ak = list(row.get('aksharas', []))
            while len(ak) < total:
                ak.append('')
            _write_row([row.get('section', ''), row.get('speed', '1'),
                        row.get('bar', '1'), row.get('row_type', 'N')] + ak[:total], f)


def convert_to_cmn(data: dict) -> str:
    """Convert ctab data dict to .cmn notation string.

    When AvartamsPerLine > 1, consecutive avartam rows are grouped onto the
    same CMN line, separated by ' || ' between groups with a final ' ||'.
    This exactly reverses what convert_cmn_to_ctab produces.
    """
    meta = data['meta']
    ti = get_thaala_index(meta.get('Thaalam', 'THRIPUTAI'))
    ji = get_jaathi_index(meta.get('Jaathi', 'CHATHUSRA'))
    anga_struct = get_anga_structure(ti, ji)
    try:
        avartams_per_line = max(1, int(meta.get('AvartamsPerLine', '1') or '1'))
    except ValueError:
        avartams_per_line = 1

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
        row_type = row.get('row_type', 'N')
        if row_type == 'N':
            note_rows[key] = row
            if key not in order:
                order.append(key)
        elif row_type == 'L':
            lyric_rows[key] = row

    def _build_avartam(aksharas):
        """Render one avartam as a CMN segment (no trailing ||)."""
        parts = []
        idx = 0
        for _, _, size in anga_struct:
            group = []
            for _ in range(size):
                cell = aksharas[idx].strip() if idx < len(aksharas) else ''
                group.append(cell if cell else '-')
                idx += 1
            parts.append(' '.join(group))
        return ' | '.join(parts)

    prev_section, prev_speed = None, None
    i = 0
    while i < len(order):
        # Collect avartams_per_line consecutive keys for one CMN line
        group_keys = order[i:i + avartams_per_line]
        section, speed, _ = group_keys[0]

        if section != prev_section:
            lines.append(f"{{ {section}:")
            prev_section = section
        try:
            speed_val = float(speed)
        except (TypeError, ValueError):
            speed_val = 1.0
        speed_text = (
            str(int(speed_val)) if speed_val.is_integer()
            else str(speed_val))
        if speed_val != prev_speed:
            lines.append(f"#S{speed_text}")
            prev_speed = speed_val

        # Build note line: avartam1 || avartam2 || ...
        note_segments, lyric_segments = [], []
        for key in group_keys:
            nr = note_rows.get(key)
            lr = lyric_rows.get(key)
            note_segments.append(
                _build_avartam(nr.get('aksharas', [])) if nr else _build_avartam([]))
            lyric_segments.append(
                _build_avartam(lr.get('aksharas', [])) if lr else None)

        lines.append(' || '.join(note_segments) + ' ||')
        if any(s is not None for s in lyric_segments):
            lyric_line = ' || '.join(
                s if s is not None else _build_avartam([])
                for s in lyric_segments) + ' ||'
            lines.append('{ ' + lyric_line)

        i += avartams_per_line

    return '\n'.join(lines)


# ── CMN → CTAB converter ──────────────────────────────────────────────────────

# Matches a CMN command line: #T4, #J2, #M15, #S1, #D60 …
_CMD_RE = _re.compile(r'^\s*#([DIJMNPST])(\d+(?:\.\d+)?)')

# Regex to resolve a single generic swara token: bare note letter + optional octave marker
# Matches tokens like 'R', 'G', 'D' (no digit) with optional .  ' ^ suffix
_GENERIC_NOTE_RE = _re.compile(r'^([SRGMPDNsrgmpdn])([\.\'\^]?)$')

# Matches individual note tokens in a CMN notation line.
# Handles: S, R2, G3, M2', D., N^, S', G3- (glide); also , ; and standalone -
# A trailing '-' (glide marker) is captured as part of the note token so it
# is not treated as a separate rest; the resolver strips it later.
_CMN_NOTE_RE = _re.compile(
    r'([SsRrGgMmPpDdNn][1-4]?[\.\'\^]?-?|[,;\-])'
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
            key = m.group(1)
            value_text = m.group(2)
            val = float(value_text) if key == 'S' else int(value_text)
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
                current_speed = (
                    str(int(val)) if val.is_integer() else str(val))
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

    # ── Raaga-aware note resolution ───────────────────────────────────────────
    ragam = meta.get('Ragam', '').strip()
    note_map: dict = {}
    if ragam:
        try:
            matches = _raaga_module.search_for_raaga_by_name(ragam, is_exact=True)
            if not matches:
                matches = _raaga_module.search_for_raaga_by_name(ragam, is_exact=False)
            if matches:
                raaga_id = matches[0][0]
                aro  = _raaga_module.get_aaroganam(raaga_id)
                avro = _raaga_module.get_avaroganam(raaga_id)
                # aarohanam takes priority (processed last → overwrites avro entries)
                for note in (avro + aro):
                    clean = note.replace('^', '').replace("'", '').replace('.', '')
                    if not clean:
                        continue
                    base = clean[0].upper()
                    if base not in note_map:
                        note_map[base] = clean   # e.g. 'R' → 'R2', 'D' → 'D2'
        except Exception:
            note_map = {}   # fall back to no resolution on any error

    def _resolve_token(token: str) -> str:
        """Resolve a CMN token to a CTAB-compatible note.

        Conversions applied (in order):
        1. Punctuation / rest tokens (, ; -) pass through unchanged.
        2. Trailing '-' (glide marker) is stripped – it is a performance cue
           only and has no meaning in the CTAB grid.
        3. '^' (caret = upper octave in legacy CMN) is replaced with "'"
        4. Lowercase base letter → mandra sthayi: add '.' suffix unless an
           explicit octave marker is already present.
        5. For digit-qualified tokens that are already specific (e.g. 'R2',
           'G3.') no raaga-map lookup is performed.
        6. Generic bare-letter tokens (e.g. 'R', 'D') are resolved through
           the raaga note_map (e.g. 'R' → 'R2').
        """
        if not token or token in (',', ';', '-'):
            return token
        # Strip trailing glide marker
        if token.endswith('-'):
            token = token[:-1]
        if not token:
            return ''
        # Legacy caret → upper-octave apostrophe
        token = token.replace('^', "'")
        # Digit-qualified tokens (e.g. 'R2', "G3'", 'r2')
        if len(token) >= 2 and token[1].isdigit():
            if token[0].islower():
                # Mandra sthayi: lowercase base + digit, no explicit octave
                upper = token[0].upper() + token[1:]
                if not upper.endswith(('.', "'")):
                    upper += '.'
                return upper
            return token   # already fully specified (e.g. 'R2', "D2'")
        # Generic single letter (possibly with octave suffix)
        m = _GENERIC_NOTE_RE.match(token)
        if not m:
            return token
        base, suffix = m.groups()
        is_lower = base.islower()
        if not note_map:
            # No raaga – just normalise case/octave
            if is_lower and not suffix:
                return base.upper() + '.'
            return base.upper() + suffix
        resolved = note_map.get(base.upper(), base.upper())
        # Lowercase without explicit octave marker → mandra sthayi
        if is_lower and not suffix:
            suffix = '.'
        return resolved + suffix

    # Build CTAB rows
    total_aks = get_total_aksharas(thaala_idx, jaathi_idx)
    for row in rows:
        notes  = (row.get('notes',  []) + [''] * total_aks)[:total_aks]
        lyrics = (row.get('lyrics', []) + [''] * total_aks)[:total_aks]

        # Apply raaga-aware resolution to every note token
        notes = [_resolve_token(n) for n in notes]

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
