# PyCarnatic – Design Document

## Table of Contents
1. [Carnatic Music Theory Background](#carnatic-music-theory-background)
2. [Raaga System Design](#raaga-system-design)
3. [ThaaLa System Design](#thaala-system-design)
4. [Notation System (CMN Format)](#notation-system-cmn-format)
5. [Notation Parser Design](#notation-parser-design)
6. [Lesson Generation Design](#lesson-generation-design)
7. [MIDI Pipeline Design](#midi-pipeline-design)
8. [AI Generation Design](#ai-generation-design)
9. [Frequency and Pitch Model](#frequency-and-pitch-model)
10. [Gamaka (Ornament) Design](#gamaka-ornament-design)

---

## Carnatic Music Theory Background

Carnatic music uses a 7-note scale system: **Sa Ri Ga Ma Pa Da Ni** (S R G M P D N), analogous to Do Re Mi Fa Sol La Ti.

### The 72 Melakartha System
The Melakartha is a set of 72 "parent" raagas that cover all mathematically possible permutations of the 12-note chromatic scale within the Carnatic framework:
- **Sa (S)** and **Pa (P)** are fixed — they never change.
- **Ma (M)** has 2 variants: M1 (shuddha/perfect 4th) and M2 (prathi/augmented 4th). The 72 are split into two groups of 36.
- **Ri (R)**, **Ga (G)**, **Da (D)**, **Ni (N)** each have 3 variants. Specific combinations are assigned to each Melakartha.

### Janya Raagas
Janya (derived) raagas are scales derived from a Melakartha parent by:
- **Omitting** one or more notes from the ascending (Aaroganam) or descending (Avaroganam) scale.
- **Reordering** notes (vakra — crooked phrases).
- A raaga is classified as **Sampoorna** (complete) if it uses all 7 notes in both directions.

PyCarnatic stores approximately 400 raagas (Melakarthas + popular Janyas) in `config/raaga_list.inp`.

---

## Raaga System Design

### Raaga Dictionary (`settings.RAAGA_DICT`)
The Raaga list is parsed from `carnatic/config/raaga_list.inp` at startup into a Python dictionary indexed by integer ID:

```python
RAAGA_DICT = {
    0: {
        "Name": "MAyamAlava Gowla",
        "Melakartha": "15",
        "Aroganam": "S R1 G3 M1 P D1 N3 S",
        "Avaroganam": "S N3 D1 P M1 G3 R1 S",
        "Aroganam Note Count": "8",
        "Avaroganam Note Count": "8",
        "IsJanya": "No",
        "Parent": ""
    },
    ...
}
```

### Note Variant Resolution
When a lesson template contains a generic note like `R`, `G`, `M`, `D`, or `N`, `cparser` resolves it to the correct variant for the active Raaga by looking it up in `RAAGA_DICT[RAAGA_INDEX]["Aroganam"]`.

For example, if the Raaga has `R1` in its Aaroganam, the template note `R` resolves to `R1`. If both `R1` and `R2` appear (a vakra raaga), the notation file must specify the variant explicitly.

### Raaga List Filtering (`RAAGA_LIST_SELECTION`)
The UI raaga dropdown is filtered at startup according to the `raaga_list_index` parameter:

| Value | Filter |
|---|---|
| 0 | Melakartha raagas only |
| 1 | Sampoorna raagas only (8 notes) |
| 2 | Raagas with 6 or more notes (default) |
| 3 | All raagas from the input file |

---

## ThaaLa System Design

### The 35 ThaaLa System
Carnatic rhythm (ThaaLa) is defined by three dimensions:

| Dimension | Options | Count |
|---|---|---|
| **ThaaLa** | Eka, Roopaka, Jampa, Thriputai, Mathya, Ata, Dhurva | 7 |
| **Jaathi** | Thisra (3), Chathusra (4), Khanda (5), Misra (7), Sankeerna (9) | 5 |
| **Nadai** | 1st Kalai, 2nd Kalai, Thisra, Chathusra, Khanda, Misra, Sankeerna | 7 |

The product of ThaaLa × Jaathi gives 35 base combinations. Nadai further subdivides each beat.

### Akshara Count
The total akshara count (beats per cycle) is computed by `thaaLa.total_akshara_count(thaaLa_index, jaathi_index, nadai_index)`.  
This value drives lesson generation — lessons are padded or trimmed to fit exactly one or two Avarthanams (ThaaLa cycles).

### Solkattu Generation
Solkattu are spoken syllables (ta, ka, di, mi, tha, num, etc.) that represent mridangam strokes. `thaaLa.py` generates the syllable pattern for any ThaaLa/Jaathi/Nadai combination and `cparser.parse_solkattu_file()` converts them to a playable MIDI percussion track.

---

## Notation System (CMN Format)

Files use the `.cmn` (Carnatic Music Notation) extension. They are plain UTF-8 text.

### Line Types

| Line type | Starts with | Purpose |
|---|---|---|
| Comment | `{` | Ignored — free-form text |
| Command | `#` | Set tempo, instrument, speed, ThaaLa etc. |
| Direction | `U` or `D` | Play next line in upper or lower octave |
| Silent marker | `$` | Insert silence (rest) |
| Note line | Note character | Sequence of Carnatic notes |

### Note Token Grammar

A single note token matches the following pattern:
```
([SsPpRrGgMmDdNn][1-4]?[.'^]?[</!~>]?[1-5]?)
```

Broken down:

| Part | Matches | Description |
|---|---|---|
| `[SsRrGgMmPpDdNn]` | Note letter | The 7 Carnatic notes (case-insensitive) |
| `[1-4]?` | Variant number | R1, R2, G2, G3, M1, M2, D1, D2, N2, N3 |
| `[.'^]?` | Octave suffix | `.`=lower, `'`/`^`=upper |
| `[<>]?` | Microtone direction | `>` = sharper, `<` = flatter |
| `[1-5]?` | Microtone amount | 1=10%, 2=20%, 3=30%, 4=40%, 5=50% |
| `~` | Shake gamaka | Oscillate on the note |
| `/` | Glide-up separator | Glide from previous note to next |
| `!` | Glide-down separator | Glide down from previous note to next |
| `,` | Duration extend | +1 akshara |
| `;` | Duration extend | +2 aksharas |

### Duration Model
The base duration of a note is: `1 / (TEMPO/60)` seconds × nadai_factor.  
Each `,` adds one more base unit; each `;` adds two. This is computed by `cparser._get_duration()`.

---

## Notation Parser Design

`cparser.parse_notation_file(file, arrange_notes_to_speed_and_thaaLa)` is the main parsing entry point.

### Parsing Pipeline

```
Read file line by line
    │
    ├─ Comment? → skip
    ├─ Command (#D, #S, #M, #T, #J, #N, #I)? → update settings globals
    ├─ Direction (U/D)? → set octave context for next line
    └─ Note line? → tokenize with regex → _parse_one_note() per token
                         │
                         ▼
                 (note, octave, variant, microtone, gamaka, duration)
                         │
                         ▼
              _note_to_midi_pitch(note, octave, variant, raaga_index)
                         │
                         ▼
              Append (note_char, (instrument_idx, midi_pitch, duration_secs))
                         │
                         ▼
              Return scamp_note_list
```

### Note-to-MIDI Pitch Conversion
`_note_to_midi_pitch()` maps the Carnatic note + variant to a MIDI pitch number:
1. Look up the 12-note chromatic index for the note (e.g. `S`=60, `R1`=62, `R2`=63 in kattai 4.5).
2. Apply the Kattai (shruthi) offset: `midi_pitch = base_pitch + (kattai - 4.5) * 2`.
3. Apply octave shift: lower octave −12, upper octave +12.
4. Apply microtone bend (stored separately as pitch-bend data).

---

## Lesson Generation Design

### Template-Based Generation
Each lesson type (SaraLi, Jantai, etc.) has a set of template files in `carnatic/config/`:
```
config/SaraLi/saraLivarisai_n8_a16.inp   ← 8-note raaga, 16-akshara ThaaLa
config/Jantai/jantaivarisai_n7_a12.inp   ← 7-note raaga, 12-akshara ThaaLa
```

The file selected is determined by:
- `n` = number of notes in the Raaga's Aaroganam
- `a` = total akshara count of the ThaaLa/Jaathi combination

### Note Substitution
Templates use generic `S R G M P D N` notation. When `cparser` parses the file, it resolves each generic note to the correct Raaga-specific variant using `settings.RAAGA_DICT`.

### Speed Arrangement
If `arrange_notes_to_speed_and_thaaLa=True`, the parser expands the note list to fill one Avarthanam by repeating or stretching notes according to the current Nadai setting.

### Alankaara Generation (from book)
Reads from `config/Alankaaram/alankaaram_<thaaLa>.inp` — one file per ThaaLa type — and adapts the pattern to the Raaga's notes.

### Alankaara Generation (from algorithm)
Algorithmically generates all permutation patterns of the Raaga's notes that fit into the chosen ThaaLa cycle, without relying on pre-built templates.

---

## MIDI Pipeline Design

### Note List → MIDI File

`cmidi.write_to_midifile_from_scamp_notes()` converts the parser output into a standard MIDI file:

```
scamp_note_list = [
    ('S',  (0,  60, 0.25)),   # instrument 0 (Veena), MIDI 60, 0.25 sec
    ('R1', (0,  62, 0.25)),
    ('$',  (0,   0, 0.25)),   # rest/silence
    ...
]
```

For each non-silent note:
1. `addProgramChange(track=0, channel=0, program=instrument_index)` — selects MIDI instrument.
2. `addNote(track, channel, pitch, time, duration, volume)` — places note at cumulative time offset.

For percussion (Track 1):
- A second MIDI track is written with the Solkattu pattern from `thaaLa`.
- Percussion uses MIDI channel 9 conventions (General MIDI drum map).

### Temp File Strategy
The MIDI file is written to `carnatic/tmp/output.mid` before playback. This directory is auto-created by `settings.py` on import. The file is overwritten on each play action.

### SoundFont Playback
`MPlayer` (extends `sf2_loader`):
1. Calls `sf2_loader.play_midi_file(midi_file)` which internally uses the loaded `.sf2` SoundFont.
2. A `pygame.event.poll()` loop keeps the GUI responsive during playback.
3. `pause()` / `resume()` delegate to `sf2_loader.pause()` / `sf2_loader.unpause()`.

---

## AI Generation Design

### Markov Chain (`cmarkov.py`)

**Algorithm:**
1. Read corpus files → extract note sequence via `cparser._get_notes_from_file()`.
2. Build bigrams: `[(S, R1), (R1, G3), (G3, M1), ...]`
3. For each note, compute conditional probability: `P(next | current)` from bigram counts.
4. Random walk: start from `starting_note`, repeatedly sample the next note from the probability distribution.
5. Append `ending_note` if specified.

**Extended Markov (`cmarkovn.py`):**  
Uses n-grams of configurable `width` (1–4) — e.g., width=2 builds trigrams `(S R1, R1 G3)`. This captures slightly longer-range melodic patterns.

### LSTM Deep Learning (`cdeeplearn.py`)

**Model Architecture:**
```
Input: one-hot encoded note sequences of length seq_length
    │
    ▼
LSTM layer (128 units)
    │
    ▼
Dense layer (64 units, ReLU)
    │
    ▼
Dense output layer (num_unique_notes, Softmax)
    │
    ▼
Output: probability distribution over all notes in the vocabulary
```

**Training Pipeline:**
1. Notes are extracted from corpus/lesson files and encoded as integer indices.
2. Sliding-window sequences of length `seq_length` are built as training pairs.
3. Model trains for `number_of_epochs` (default 90) with batch size (default 16).
4. Weights are saved to `model_weights/<raaga_name>.h5` and the note vocabulary to `<raaga_name>.json`.
5. On subsequent runs, saved weights are loaded (unless `perform_training=True`).

**Generation:**
- Seed with `starting_note`; iteratively predict and sample the next note.
- Generated notes are post-processed by `lessons.generate_kalpana_swarams()` to fit the selected ThaaLa cycle.

**Lazy Import Strategy:**  
Keras/TensorFlow are imported **inside** `_get_model()` and `_make_model()`, not at the top of the file. This prevents import-time crashes when TensorFlow is not installed, allowing the rest of the application to run normally.

---

## Frequency and Pitch Model

`settings.py` stores three pitch systems:

| System | Notes | Use |
|---|---|---|
| 12-note equal temperament | Standard MIDI pitches | SF2_LOADER playback |
| 16-note system | Adds komal and tivra variants | Extended microtone mapping |
| 22-shruti system | Traditional Indian microtonal divisions | Research / SCAMP playback |

For the SF2_LOADER pipeline, pitch is expressed as standard MIDI note numbers (60 = Middle C). Microtone adjustments are encoded as MIDI pitch-bend values using:
```
pitch_bend = 4096 * 12 * log2(desired_freq / base_freq)
```

The Kattai (Shruthi) setting shifts the entire pitch map: each half-kattai = 1 semitone offset.

---

## Gamaka (Ornament) Design

Gamakas are melodic ornaments central to Carnatic music expression. PyCarnatic supports:

| Gamaka | Notation | Implementation |
|---|---|---|
| **Glide up (Jaaruswaranam)** | `S / R` | SCAMP `Envelope`: pitch ramps linearly from S to R over the combined duration |
| **Glide down** | `M ! P` | SCAMP `Envelope`: pitch ramps down from M to P |
| **Shake (Kampitham)** | `S~` | SCAMP `Envelope`: pitch oscillates above/below S at a set rate |

These are implemented in `cparser` by detecting the `/`, `!`, or `~` tokens and constructing a SCAMP `Envelope` object instead of a fixed pitch value. The envelope is passed to `scamp.Instrument.play_note()`.

> **Important:** The SF2_LOADER + MIDI pipeline does not support envelopes. Notes with gamaka markers are played at their base pitch without the ornament when using the default player. Switch to the SCAMP player to hear gamakas.

