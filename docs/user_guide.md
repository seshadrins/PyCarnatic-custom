# PyCarnatic – Carnatic Music Guru: User Guide

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Installation](#installation)
3. [Running the Application](#running-the-application)
4. [Application Window Overview](#application-window-overview)
5. [Toolbar Reference](#toolbar-reference)
6. [Menu Reference](#menu-reference)
7. [The Notation Editor](#the-notation-editor)
8. [Generating Lessons](#generating-lessons)
9. [Playing Music](#playing-music)
10. [Kalpana Swaram (AI Improvisation)](#kalpana-swaram)
11. [Raaga Search](#raaga-search)
12. [Krithi Player](#krithi-player)
13. [Raagam Quiz](#raagam-quiz)
14. [File Operations](#file-operations)
15. [Language Selection](#language-selection)

---

## System Requirements

| Requirement | Details |
|---|---|
| Operating System | Windows 10/11 (64-bit) |
| Python | 3.13+ (64-bit) |
| RAM | 4 GB recommended |
| Disk Space | ~500 MB (includes SoundFont files) |
| Audio | Working audio output device |

---

## Installation

### 1. Create and activate a virtual environment

```powershell
cd C:\CarnaticMusic\PyCarnatic
python -m venv venv
venv\Scripts\Activate.ps1
```

### 2. Install the package and all dependencies

```powershell
pip install -e .
pip install PyQt6 audioop-lts
```

> **Note:** `audioop-lts` is required on Python 3.13+ because the built-in `audioop` module was removed. Without it, the SoundFont audio engine will fail to start.

### 3. Optional dependencies

| Package | Feature enabled |
|---|---|
| `python-rtmidi` | Live MIDI keyboard input/output |
| `pynput` | Mouse and keyboard hooks |
| `tensorflow` | Deep Learning Kalpana Swaram generation |

---

## Running the Application

**Recommended (using venv):**
```powershell
venv\Scripts\python.exe cli.py
```

**Or activate venv first, then run normally:**
```powershell
venv\Scripts\Activate.ps1
python cli.py
```

> ⚠️ Do **not** use `conda run python cli.py`. The base Conda environment does not have the required packages.

---

## Application Window Overview

The Carnatic Music Guru window has three main areas:

1. **Three toolbars** at the top — playback controls, Raaga/instrument selection, and ThaaLa settings
2. **Menu bar** — access all features and file operations
3. **Notation editor** (central area) — a text area where you write or view Carnatic notation

---

## Toolbar Reference

### Toolbar 1 — Playback & Quick Actions

| Button | Action |
|---|---|
| 📄 New file | Clear the notation editor |
| 📂 Open file | Open a `.cmn` notation file |
| ▶ Play | Play the notes in the editor |
| ⏸ Pause/Resume | Pause or resume playback |
| ⏹ Stop | Stop playback |
| Veena icon | Switch instrument to Veena |
| Violin icon | Switch instrument to Violin |
| Flute icon | Switch instrument to Flute |
| Mridangam icon | Toggle percussion layer on/off |
| 🔍 Search | Open Raaga Search dialog |
| 🎵 Music Player | Open the Krithi (song) player |

### Toolbar 2 — Tempo, Shruthi & Raaga

| Control | Description |
|---|---|
| **Duration** (spin box) | Tempo in BPM (1–200). Default: 60 |
| **Shruthi** (dropdown) | Pitch/Kattai setting (1.0 to 6.5). Default: 4.5 |
| **Instrument** (dropdown) | Select the melodic instrument |
| **Raaga** (dropdown) | Select the Raaga |

### Toolbar 3 — Rhythm Settings

| Control | Description |
|---|---|
| **Percussion instrument** | Mridangam or Thavil |
| **ThaaLa** | Rhythm cycle (Eka, Roopaka, Jampa, Thriputai, Mathya, Ata, Dhurva) |
| **Jaathi** | Beat subdivision (Thisra, Chathusra, Khanda, Misra, Sankeerna) |
| **Nadai** | Speed/gait of the rhythm |
| Raaga info label | Shows Aaroganam and Avaroganam of the current Raaga |
| ThaaLa info label | Shows beat-position markers for the current ThaaLa |

---

## Menu Reference

### File Menu

| Item | Action |
|---|---|
| New | Clear the notation editor |
| Open | Open a `.cmn` file |
| Close | Close the current file |
| Save | Save the current notation |
| Save as Audio | Export the notation as an audio file |
| Exit | Exit the application |

### Raagam Menu

| Item | Action |
|---|---|
| Search Raaga | Open the Raaga search tool |
| Generate → Sarali Varisai | Generate Sarali Varisai lesson notes |
| Generate → Jantai Varisai | Generate Jantai Varisai lesson notes |
| Generate → Dhaattu Varisai | Generate Dhaattu Varisai lesson notes |
| Generate → Mel Sthaayi Varisai | Generate upper-octave lesson notes |
| Generate → Keezh Sthaayi Varisai | Generate lower-octave lesson notes |
| Generate → Alankaara (from book) | Generate Alankaara for all 35 ThaaLas |
| Generate → Alankaara (algorithm) | Generate algorithmically for any ThaaLa |
| Generate → Kalpana Swaram (corpus) | AI improvisation from notation corpus files |
| Generate → Kalpana Swaram (lessons) | AI improvisation learned from lesson patterns |

### Play Menu

| Item | Action |
|---|---|
| Play Aaroganam / Avaroganam | Play the ascending and descending scale of the selected Raaga |
| Play Sarali Varisai | Play the first lesson type |
| Play Jantai Varisai | Play the second lesson type |
| Play Dhaattu Varisai | Play the third lesson type |
| Play Mel Sthaayi Varisai | Play the upper-octave variation |
| Play Keezh Sthaayi Varisai | Play the lower-octave variation |
| Play Alankaara (from book) | Play Alankaara patterns as in music books |
| Play Alankaara (algorithm) | Play algorithmically generated Alankaara |
| Play Geetham | Browse and play a Geetham composition |
| Play Varnam | Browse and play a Varnam composition |
| Play Swarajaathi | Browse and play a Swarajaathi composition |
| Play Voice Practice | Play voice practice exercises |
| Play Raaga Practice | Play Raaga practice exercises |

### ThaaLam Menu

| Item | Action |
|---|---|
| Play Selected ThaaLam | Play the percussion pattern for the selected ThaaLa/Jaathi |
| Play Solkattu | Play spoken syllables (ta ka di mi etc.) for the current ThaaLa |
| Play Lessons | Browse and play ThaaLa percussion lessons |
| Play Metronome | Start a metronome at the current tempo |

### Tools Menu

| Item | Action |
|---|---|
| Options | Application settings |
| Raagam Quiz | Interactive quiz to identify raagas by ear |
| Volume | Adjust playback volume |
| Change Language | Switch UI language (English / Tamil / Telugu) |
| Krithi Player | Open the dedicated song player |

---

## The Notation Editor

The central text area is where you write Carnatic notation in `.cmn` format.

### Quick Start Example

```
{ MAyamAlava Gowla - Sarali Varisai
#D60
S R1 G3 M1 P D1 N3 S'
S' N3 D1 P M1 G3 R1 S
```

### Notation Syntax Reference

#### Comments
Lines beginning with `{` are treated as comments and ignored during playback.
```
{ This is a comment
```

#### Commands (lines beginning with `#`)

| Command | Description | Example |
|---|---|---|
| `#D<n>` | Duration / Tempo (BPM, 1–200) | `#D72` |
| `#S<n>` | Song speed (1–5) | `#S2` |
| `#M<n>` | Melakartha number (1–72) | `#M29` |
| `#T<n>` | ThaaLa (1=Eka … 7=Dhurva) | `#T4` |
| `#J<n>` | Jaathi (1=Thisra … 5=Sankeerna) | `#J2` |
| `#N<n>` | Nadai / speed subdivision | `#N3` |
| `#I<n>` | Instrument index | `#I0` |

#### Notes

| Symbol | Meaning |
|---|---|
| `S` | Shadjam (Sa) |
| `R` or `R1`/`R2` | Rishabham (choose variant for raaga) |
| `G` or `G2`/`G3` | Gandharam |
| `M` or `M1`/`M2` | Madhyamam |
| `P` | Panchamam (Pa) |
| `D` or `D1`/`D2` | Dhaivatham |
| `N` or `N2`/`N3` | Nishadam |

#### Octaves

| Suffix | Octave |
|---|---|
| `.` (period/dot) | Lower octave — e.g. `S.` `R1.` |
| *(none)* | Middle octave — e.g. `S` `R1` |
| `'` or `^` | Upper octave — e.g. `S'` `R1^` |

#### Duration Modifiers

| Symbol | Effect |
|---|---|
| `,` (comma) | Extend note by one extra akshara |
| `;` (semicolon) | Extend note by two extra aksharas |
| Example: `S,,` | Sa held for 3 aksharas total |

#### Gamakas (ornaments) — SCAMP Player only

| Notation | Gamaka Type |
|---|---|
| `S / R` | Glide up from S to R |
| `M ! P` | Glide down from M to P |
| `S~` | Shake/oscillate on S |

#### Microtones

| Notation | Meaning |
|---|---|
| `S>1` | 10% sharper than S |
| `S>2` | 20% sharper than S |
| `G3<1` | 10% flatter than G3 |
| `M2<4` | 40% flatter than M2 |

> ⚠️ Gamakas and microtones require the **SCAMP Player**. The default SF2_LOADER player ignores them.

---

## Generating Lessons

1. Select a **Raaga** from the Raaga dropdown.
2. Select a **ThaaLa** and **Jaathi** from the rhythm dropdowns.
3. Go to **Raagam → Generate → [Lesson Type]**.
4. The notation is written into the editor.
5. Click **▶ Play** or go to **Play → [Same Lesson Type]** to hear it.

### Lesson Types

| Lesson | Description |
|---|---|
| **Sarali Varisai** | Basic ascending/descending scale patterns |
| **Jantai Varisai** | Repeated-note (double-note) exercises |
| **Dhaattu Varisai** | Skipping-note pattern exercises |
| **Mel Sthaayi Varisai** | Upper-octave scale exercises |
| **Keezh Sthaayi Varisai** | Lower-octave scale exercises |
| **Alankaara (from book)** | Rhythmic pattern exercises across all 35 ThaaLas |
| **Alankaara (algorithm)** | Computer-generated Alankaara for any ThaaLa/Jaathi |

---

## Playing Music

1. Type or open notation in the editor.
2. Set **Tempo (BPM)**, **Shruthi (Kattai)**, and **Instrument** in Toolbar 2.
3. Click **▶ Play** to start.
4. Use **⏸ Pause/Resume** and **⏹ Stop** as needed.

> **Note:** Pause/Resume is only supported by the **SF2_LOADER** player (the default). The SCAMP player does not support pause.

---

## Kalpana Swaram

Kalpana Swaram is AI-based improvisation that generates new note sequences in the style of a given Raaga.

### Generating from Lessons
1. Select a Raaga, ThaaLa, and Jaathi.
2. Go to **Raagam → Generate → Kalpana Swaram (lessons)**.
3. The AI learns from the existing lessons (Jantai, Dhaattu, Alankaara etc.) for that Raaga and generates a new sequence.

### Generating from Corpus Files
1. Go to **Raagam → Generate → Kalpana Swaram (corpus)**.
2. You will be prompted to select corpus notation files (`.cmn` files of existing compositions).
3. The AI learns the note patterns from those files and generates a new sequence.

### AI Methods
- **Markov Chain** (default) — Fast. Learns bigram (note-pair) probabilities. Good for short phrases.
- **Deep Learning (LSTM)** — Slower. Requires TensorFlow. Captures longer melodic patterns.

---

## Raaga Search

1. Click the **🔍 Search** button in Toolbar 1 or go to **Raagam → Search Raaga**.
2. Search by name, Melakartha number, or attributes (e.g., note count, specific notes in Aaroganam).
3. Select a Raaga from the results to apply it to the session.

---

## Krithi Player

The Krithi Player lets you browse and play composed songs (Geethams, Varnams, Swarajaathis):
1. Go to **Tools → Krithi Player** or click the **🎵** toolbar button.
2. Browse available compositions.
3. Select a composition and click Play.

---

## Raagam Quiz

1. Go to **Tools → Raagam Quiz**.
2. The app plays a sequence of notes and asks you to identify the Raaga.
3. Select your answer from the options provided.

---

## File Operations

| Operation | How |
|---|---|
| **New** | File → New (or toolbar button). Clears the editor. |
| **Open** | File → Open. Opens a `.cmn` notation file. |
| **Save** | File → Save. Saves the current notation. |
| **Export Audio** | File → Save as Audio. Exports the current notation as an MP3 file. |

---

## Language Selection

1. Go to **Tools → Change Language**.
2. Select **Tamil** or **Telugu** (the current language is not shown in the sub-menu).
3. The application will restart with the selected language.

Available languages: English (`en`), Tamil (`ta`), Telugu (`te`).

