# PyCarnatic – Architecture Document

## Table of Contents
1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Module Breakdown](#module-breakdown)
4. [Data Flow](#data-flow)
5. [Player Backends](#player-backends)
6. [Configuration System](#configuration-system)
7. [File and Directory Structure](#file-and-directory-structure)
8. [Inter-Module Dependencies](#inter-module-dependencies)

---

## Overview

PyCarnatic (Carnatic Music Guru) is a Python desktop application built with PyQt6. It provides:
- A structured notation editor for Carnatic music (`.cmn` files)
- Music lesson generation for any Raaga and ThaaLa combination
- Audio playback using SoundFont (SF2) or SCAMP synthesizers
- AI-based improvisation (Kalpana Swaram) via Markov chains or LSTM deep learning

The application is organized as a Python package (`carnatic/`) driven by a thin entry-point (`cli.py`).

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        cli.py (entry point)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ calls show_ui()
┌───────────────────────────▼─────────────────────────────────────┐
│                  carnatic/ui/tutor.py  (TutorUI)                │
│              PyQt6 Main Window — menus, toolbars, editor        │
└──┬──────────────┬─────────────────┬──────────────┬─────────────┘
   │              │                 │              │
   ▼              ▼                 ▼              ▼
raaga.py     thaaLa.py         lessons.py     cmidi.py
(Raaga DB)  (Rhythm DB)     (Lesson Generator) (MIDI Player)
   │              │                 │              │
   └──────────────┴────────┬────────┘              │
                           ▼                       │
                       cparser.py  ───────────────►│
                    (Notation Parser)               │
                           │                       │
                    settings.py ◄──────────────────┘
                   (Global Config)
```

---

## Module Breakdown

### `cli.py`
The application entry point. Calls `carnatic.ui.tutor.show_ui()` with no arguments, using defaults (English, SF2_LOADER player, raagas with 6+ notes).

### `carnatic/ui/tutor.py` — `TutorUI`
The main PyQt6 `QMainWindow`. Responsibilities:
- **Toolbar creation**: Three toolbars for playback, Raaga/instrument selection, and ThaaLa/Jaathi/Nadai settings.
- **Menu creation**: File, Raagam, Play, ThaaLam, Tools, Help menus.
- **Signal wiring**: All UI events are connected to handler methods inside `TutorUI`.
- **Playback orchestration**: Calls `cmidi` functions in background threads; manages pause/resume/stop state.
- **Lesson display**: Generates notation text via `lessons.py`, writes it to the editor (`QTextEdit`).

### `carnatic/ui/krithi_player.py`
A secondary dialog that allows browsing and playing pre-composed Geethams, Varnams, and Swarajaathis.

### `carnatic/raaga.py`
Raaga database and query API:
- Loads the full Raaga dictionary from `settings.RAAGA_DICT` (read from `config/raaga_list.inp`).
- Provides functions: `get_raaga_list()`, `set_raagam()`, `get_aaroganam()`, `get_avaroganam()`, `get_next_note()`, `get_previous_note()`, `search_for_raaga_by_name()`, `search_for_raaga_by_attributes()`, `get_janya_raagas()`, `get_melakartha_raagas()`.
- The Raaga dictionary keys include: `Name`, `Melakartha`, `Aroganam`, `Avaroganam`, `Aroganam Note Count`, `Avaroganam Note Count`, `IsJanya`, `Parent`.

### `carnatic/thaaLa.py`
Rhythm system database and query API:
- Encodes the 7 ThaaLas × 5 Jaathis = 35 ThaaLa combinations.
- Provides: `get_thaaLam_names()`, `get_jaathi_names()`, `get_nadai_names()`, `set_thaaLam()`, `get_thaaLa_positions()`, `total_akshara_count()`.
- Also generates Solkattu (spoken percussion syllables) patterns for mridangam accompaniment.

### `carnatic/lessons.py`
Lesson notation generator:
- Reads pre-built template files from `carnatic/config/` (SaraLi, Jantai, Dhaattu, Mel/Keezh Sthaayi, Alankaara).
- Adapts templates to the selected Raaga by substituting the correct note variants (R1/R2, G2/G3, etc.).
- Calls `cparser.parse_notation_file()` to expand the template into a full note list.
- Calls `cmarkov` or `cdeeplearn` for Kalpana Swaram generation via `generate_kalpana_swarams()`.

### `carnatic/cparser.py`
The core notation engine:
- Parses `.cmn` text files line by line using compiled regex patterns.
- Processes: comments (`{`), commands (`#D`, `#S`, `#M`, `#T`, `#J`, `#N`, `#I`), and note lines.
- Converts each note symbol (e.g. `R1.~`) into a tuple: `(instrument_index, midi_pitch, duration_seconds)`.
- Outputs a SCAMP-compatible note list used by both player backends.

### `carnatic/cmidi.py`
The MIDI/SoundFont player backend:
- `MPlayer` class extends `sf2_loader` to manage play/pause/resume/stop state.
- `write_to_midifile_from_scamp_notes()`: converts the SCAMP note list into a standard MIDI file using `midiutil`.
- `_write_to_midi_and_play()`: writes to a temp file then plays via `MPlayer`.
- Handles optional percussion layer (a second MIDI track).

### `carnatic/cplayer.py`
The SCAMP player backend (alternative to cmidi):
- Uses the `scamp` library for direct audio synthesis with gamaka support.
- Supports glide envelopes and shake effects that `cmidi` ignores.
- Does **not** support pause/resume.

### `carnatic/sfplayer.py`
Helper wrapper around `sf2_loader` for direct SoundFont operations.

### `carnatic/settings.py`
Global configuration store:
- **Paths**: `_APP_PATH`, `_NOTES_PATH`, `_TEMP_PATH`, `_SOUND_FONT_FILE`, lesson/config paths.
- **State**: `RAAGA_INDEX`, `THAALA_INDEX`, `JAATHI_INDEX`, `NADAI_INDEX`, `TEMPO`, `INSTRUMENT_INDEX`, `CURRENT_INSTRUMENT`.
- **Enums**: `PLAYER_TYPE`, `THAALA_NAMES`, `JAATHI_NAMES`, `NADAI_NAMES`, `RAAGA_LIST_SELECTION`.
- **Instrument tables**: `_CARNATIC_INSTRUMENTS`, `_DEFAULT_INSTRUMENTS`, `_PERCUSSION_INSTRUMENTS`, MIDI program numbers, volume levels.
- **Frequency tables**: 12-note equal temperament, 16-note, and 22-shruti systems.
- **Regex patterns**: note pattern, command pattern, comment pattern, direction pattern.
- Auto-creates `carnatic/tmp/` on import.

### `carnatic/cmarkov.py` and `carnatic/cmarkovn.py`
Markov chain note generators:
- `cmarkov`: builds a bigram (2-note) transition probability table from corpus files and performs a random walk.
- `cmarkovn`: extended version with configurable n-gram `width` (1–4 adjacent notes).

### `carnatic/cdeeplearn.py`
LSTM deep learning note generator:
- Builds a Keras Sequential model with LSTM layers.
- Trains on note sequences from corpus or lesson files.
- Saves/loads model weights (`model_weights/` folder).
- Keras and TensorFlow are imported **lazily** (only when this feature is invoked) to avoid startup failures.

### `carnatic/raaga_search.py`
Standalone Raaga search dialog (PyQt6 `QDialog`) launched from the toolbar.

### `carnatic/song.py`
Programmatic song-building API (used by advanced / scripted usage, not directly from the GUI).

---

## Data Flow

### Playback from Editor

```
User clicks ▶ Play
    │
    ▼
TutorUI._play_notes_on_screen()
    │  reads text from QTextEdit
    ▼
cparser.parse_notation_file(temp_file)
    │  returns scamp_note_list = [(note, (instr_idx, midi_pitch, duration)), ...]
    ▼
cmidi.write_to_midifile_from_scamp_notes(scamp_note_list, "carnatic/tmp/output.mid")
    │  writes standard MIDI file
    ▼
MPlayer.play_midi_file("carnatic/tmp/output.mid")
    │  uses sf2_loader + pygame mixer
    ▼
Audio Output
```

### Lesson Generation

```
User selects Raagam → Generate → Sarali Varisai
    │
    ▼
TutorUI._generate_sarali_varisai()
    │
    ▼
lessons.__sarali_varisai(raaga_index, thaaLa_index, jaathi_index)
    │  selects template file from config/SaraLi/
    ▼
cparser.parse_notation_file(lesson_file, arrange_notes_to_speed_and_thaaLa=True)
    │  substitutes correct note variants for the chosen Raaga
    ▼
notation text written to QTextEdit
```

---

## Player Backends

| Feature | SF2_LOADER (default) | SCAMP |
|---|---|---|
| Audio quality | SoundFont-based (realistic) | Synthesis-based |
| Pause / Resume | ✅ Supported | ❌ Not supported |
| Gamakas (glide/shake) | ❌ Ignored | ✅ Supported |
| Microtones | ❌ Ignored | ✅ Supported |
| Startup speed | Fast | Slower |

The player backend is selected via `settings.PLAYER_TYPE` (default: `PLAYER_TYPE.SF2_LOADER`).

---

## Configuration System

All runtime state flows through `settings.py` as module-level globals. The UI updates these globals on every toolbar/combo-box change event, ensuring all modules always read the current selection.

Key configuration items and how they are set:

| Setting | Set by |
|---|---|
| `RAAGA_INDEX` | `raaga.set_raagam()` called from `TutorUI._raaga_selection_changed()` |
| `THAALA_INDEX` | `TutorUI._thaaLa_selection_changed()` |
| `TEMPO` | `TutorUI._duration_selection_changed()` |
| `CURRENT_INSTRUMENT` | `TutorUI._instrument_selection_changed()` |
| `NADAI_INDEX` | `TutorUI._thaaLa_selection_changed()` |

---

## File and Directory Structure

```
PyCarnatic/
├── cli.py                      # Entry point
├── pyproject.toml              # Package metadata and dependencies
├── carnatic/                   # Main package
│   ├── __init__.py
│   ├── settings.py             # Global config, paths, enums, frequency tables
│   ├── raaga.py                # Raaga DB and API
│   ├── thaaLa.py               # ThaaLa/Jaathi/Nadai DB and API
│   ├── cparser.py              # Notation parser
│   ├── cmidi.py                # SF2/MIDI player backend
│   ├── cplayer.py              # SCAMP player backend
│   ├── sfplayer.py             # sf2_loader helper
│   ├── lessons.py              # Lesson & Kalpana Swaram generator
│   ├── cmarkov.py              # Markov chain AI generator
│   ├── cmarkovn.py             # Extended Markov (n-gram) generator
│   ├── cdeeplearn.py           # LSTM deep learning generator
│   ├── raaga_search.py         # Raaga search dialog
│   ├── song.py                 # Programmatic song builder
│   ├── ui/
│   │   ├── tutor.py            # Main PyQt6 window (TutorUI)
│   │   └── krithi_player.py    # Krithi/song player dialog
│   ├── config/                 # Lesson templates & Raaga list
│   │   ├── raaga_list.inp
│   │   ├── SaraLi/
│   │   ├── Jantai/
│   │   ├── Dhaattu/
│   │   ├── mElsthaayi/
│   │   ├── KeezhSthaayi/
│   │   └── Alankaaram/
│   ├── Notes/                  # Sample notation files (.cmn)
│   ├── Lessons/                # Pre-composed songs (Geetham, Varnam, etc.)
│   ├── images/                 # UI icons
│   ├── model_weights/          # Saved LSTM weights
│   └── tmp/                    # Temporary MIDI files (auto-created)
├── docs/
│   ├── user_guide.md
│   ├── architecture.md         # This document
│   └── design.md
└── venv/                       # Python virtual environment
```

---

## Inter-Module Dependencies

```
cli.py
  └─► ui/tutor.py
        ├─► settings.py        (read/write globals)
        ├─► raaga.py           (raaga DB queries)
        ├─► thaaLa.py          (rhythm DB queries)
        ├─► lessons.py         (lesson + kalpana swaram generation)
        │     ├─► cparser.py   (notation parsing)
        │     ├─► cmarkov.py   (markov AI)
        │     ├─► cmarkovn.py  (n-gram markov AI)
        │     └─► cdeeplearn.py (LSTM AI — lazy import)
        ├─► cmidi.py           (MIDI file write + SF2 playback)
        │     └─► cparser.py
        ├─► cplayer.py         (SCAMP playback — alternative)
        └─► raaga_search.py    (search dialog)
```

