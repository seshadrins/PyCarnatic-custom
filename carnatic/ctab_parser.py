"""
Module for Tabular Notation Format (.ctab)
- Defines anga structure helpers
- Reads/writes .ctab CSV files
- Converts .ctab data to .cmn notation string for playback
"""
import csv
import os
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

