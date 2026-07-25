# Feature Proposal: Jantai Varisai and Sphuritam

## Status

Revised design proposal for review. No Jantai/sphuritam functionality has been
implemented.

## Confirmed meaning

In this feature, “Janta” means **Janta Varisai (Jantai Varisai)**:

- Swaras occur as twin-note pairs.
- The two swaras normally have the same pitch.
- The second swara is sung or played with an emphatic push.
- That emphasized second attack is the **sphuritam** gamaka.
- Beginner exercises are commonly taught in Mayamalavagowla and Adi tala, but
  the notation and playback feature should work with any selected raaga and
  thalam.

This replaces the earlier interpretation of two simultaneous thalams.

References describing the second repeated swara as stressed include:

- [Indian Heritage – Jantai Varisai](https://www.indian-heritage.org/music/abhyasa.htm)
- [Madhuraswarangal – Janta Varisai](https://www.madhuraswarangal.com/basic-lessons/janta-varisai)
- [Sāyujya – Gamaka notation](https://saayujya.com/index.php/2019/12/03/gamaka-notation/)

## User goal

Allow the tabular notation editor to represent, recognize, display, save, and
play Jantai pairs such as:

```text
S S   R R   G G   M M
```

with sphuritam applied to the second swara of each pair.

After raaga resolution in Mayamalavagowla, a generic entry could become:

```text
S S!   R1 R1!   G3 G3!   M1 M1!
```

The `!` marker in this document is a proposed plain-text representation of
sphuritam and requires approval before implementation.

## Proposed notation

### Explicit marker

Use a suffix `!` on the swara receiving sphuritam:

```text
SS!
R1R1!
G3 G3!
M1' M1'!
```

Reasons for proposing `!`:

- It visually communicates emphasis.
- It is easy to type on a standard keyboard.
- It does not conflict with the existing `~` kampitam marker.
- It survives CTAB and CMN plain-text storage.
- It can be removed cleanly for presentation-oriented spreadsheet export.

### Meaning

`G3!` means:

1. Attack the target `G3` with an emphatic second articulation.
2. Briefly approach it from an appropriate lower neighbouring pitch.
3. Settle immediately on `G3`.
4. Retain the token’s original rhythmic duration.

The exact lower approach depends on the selected raaga and must not introduce
an arbitrary chromatic pitch outside the raaga.

### Valid examples

| Notation | Meaning |
|---|---|
| `SS!` | Sa followed by sphuritam Sa |
| `R1R1!` | R1 followed by sphuritam R1 |
| `G3 G3!` | Spaced form of the same pair |
| `M1'M1'!` | Upper-octave Jantai pair |
| `.D1.D1!` | Lower-octave Jantai pair |

### Invalid or warning cases

| Notation | Handling |
|---|---|
| `S!` without a preceding matching `S` | Allow as explicit sphuritam, but show a validation warning |
| `SR1!` | Allow as explicit ornament, but do not classify it as a Jantai pair |
| `,,!` | Invalid because punctuation cannot receive sphuritam |
| `G3~!` | Reject in version 1; kampitam and sphuritam cannot be combined on one token |
| `G3!!` | Invalid duplicate marker |

## Manual and automatic workflows

### Manual notation

The user can type the `!` marker explicitly:

```text
SS!R1R1!
```

When focus leaves the cell:

- Generic swaras are resolved from the selected raaga.
- The `!` marker is preserved.
- Existing swarasthanam numbers, octave marks, spaces, and duration symbols are
  preserved.

Example for Mayamalavagowla:

```text
RR! GG! MM!  ->  R1R1! G3G3! M1M1!
```

### Jantai mode

Add a checkbox:

**Recognize Jantai pairs**

When enabled, leaving a cell detects adjacent identical swara tokens and adds
the marker to the second token:

```text
SS          -> SS!
R R         -> R1 R1!
G3G3        -> G3G3!
SSRR        -> SS!R1R1!
```

Pair matching occurs after raaga resolution and includes octave identity.
Therefore `S` and `S'` are not a pair.

Automatic recognition should operate only inside a cell in version 1. It
should not silently pair the last swara of one cell with the first swara of the
next cell.

The mode must not mark non-identical repetitions:

```text
SR  -> SR1
GG' -> G3G3'
```

## Raaga behavior

The existing multi-swara resolver should run before Jantai detection:

1. Tokenize the cell.
2. Resolve every generic swara using the selected raaga.
3. Preserve already-specific swaras.
4. Detect identical adjacent resolved tokens.
5. Add or validate sphuritam on the second token.

This makes the feature raaga-independent while still supporting the traditional
Mayamalavagowla teaching workflow.

The default Jantai lesson preset may select:

- Raaga: Mayamalavagowla
- Thalam: Chathusra-jaathi Thriputai (Adi)
- Speed: 1

These are convenience defaults, not restrictions.

## Editor interface

### Playback settings

Add:

- **Recognize Jantai pairs** checkbox
- **Sphuritam strength** control, suggested range `1–5`
- Tooltip explaining that the second identical swara receives emphasis

### Visual display

The sphuritam swara should remain editable as plain text but be visually
distinguished:

- Show `!` in the text field.
- Optionally tint or underline the second token after focus leaves the cell.
- Do not change the background color used for playback highlighting.

### Validation

On leaving a cell:

- Invalid marker placement should show a non-blocking warning style.
- Valid data must not be rewritten beyond raaga resolution and optional
  pair-marking.
- The cell length limit must expand if resolved variants and markers make the
  text longer.

## Token model

Extend the token grammar from:

```text
SWARA [octave] [kampitam]
```

to:

```text
SWARA [octave] [ornament]
ornament := "~" [distance] | "!"
```

Version 1 ornaments are mutually exclusive.

Examples of tokens:

```text
S
R1
G3'
M1~2
D1!
```

The tokenizer must continue to support:

- Concatenated swaras
- Space-separated swaras
- Comma prolongation
- Semicolon prolongation
- Upper and lower octave markers
- Existing kampitam notation

## Sphuritam playback model

Sphuritam should not be implemented as volume increase alone. The musical
effect includes an emphatic second attack and a brief lower-pitch approach.

### Proposed envelope

For a marked target swara:

1. Use a short approach segment, approximately 15–25% of the token duration.
2. Select the closest valid lower swara in the current raaga.
3. Move quickly from that pitch to the target.
4. Use a modest accent on the target attack.
5. Sustain the target for the remaining duration.

Suggested initial strength mapping:

| Strength | Approach duration | Target accent |
|---:|---:|---:|
| 1 | 10% | +5% |
| 2 | 15% | +8% |
| 3 | 20% | +12% |
| 4 | 25% | +16% |
| 5 | 30% | +20% |

These values require listening tests and should be clamped to prevent clipping.

### Raaga-aware lower neighbour

The approach pitch should use the lower neighbouring swara from the selected
raaga’s direction-aware scale:

- Use aarohanam context while ascending.
- Use avarohanam context while descending.
- Fall back to the combined raaga scale when direction is ambiguous.
- For Sa at the lower boundary, use lower-octave Nishadam when the raaga
  contains it; otherwise use a short lower pitch bend toward Sa.

The fallback rule for Sa is a review decision because traditions and
instruments may articulate sphuritam differently.

### Playback engines

#### SCAMP

SCAMP should be the reference implementation because it can express pitch and
volume envelopes:

- Strip `!` before normal pitch lookup.
- Build an approach-to-target pitch envelope.
- Apply the selected target accent.
- Preserve the original total token duration.

#### MIDI/SoundFont

The current MIDI writer emits fixed-pitch note events and cannot represent the
full envelope directly. Options:

1. Emit a short lower grace note followed by the target note.
2. Use MIDI pitch bend where channel isolation is safe.
3. Route sphuritam playback through SCAMP, as currently done for `~` kampitam.

Recommended version 1 behavior: route any score containing `!` through SCAMP.
This gives one consistent ornament implementation and avoids pitch-bend leakage
between simultaneous MIDI notes.

## Timing behavior

Sphuritam does not add a new rhythmic slot.

For `G3G3!` inside one akshara:

- The cell still contains two token slots.
- Each token receives half of the cell duration.
- The approach and target portions divide only the second token’s duration.
- Bar, thalam, percussion, and highlight timing do not change.

Comma and semicolon behavior remains unchanged.

## CTAB persistence

No new row type is needed. The `!` marker is stored with the note token:

```text
Pallavi|1|1|N|SS!|R1R1!|G3G3!|M1M1!|...
```

Add optional metadata:

```text
RecognizeJantaiPairs|True
SphuritamStrength|3
```

Rules:

- Existing CTAB files remain valid.
- Files without the new metadata default to recognition off.
- Explicit `!` tokens play even when automatic recognition is off.
- Copy, paste, save, reopen, CMN conversion, and grid rebuild must preserve the
  marker.

## Jantai lesson generation

The project already generates Jantai Varisai lesson content. The generator
should optionally emit explicit sphuritam markers on the second note of each
valid twin pair.

Proposed API:

```python
generate_lessons(
    "JANTAI_VARISAI",
    include_sphuritam=True,
)
```

Existing callers retain the current output unless they opt in, preserving
backward compatibility.

Generated generic swaras should be resolved using the requested raaga before
pair marking.

## Import and conversion

### CMN

- Extend the CMN token parser to accept `!`.
- Preserve `!` during CTAB-to-CMN and CMN-to-CTAB conversion.
- Older CMN files without the marker remain unchanged.

### CSV and XLSX

The earlier spreadsheet requirement removes gamaka notation from exported
swaras. Therefore:

- Strip `!` from Notes sheet/CSV values.
- Continue stripping `~` and its optional distance.
- Continue removing swarasthanam numbers.
- Never modify the source CTAB or editor cells during export.

Example:

```text
R1R1! G3G3!  ->  RR GG
```

## Component changes

### `carnatic/ui/tabular_editor.py`

- Extend note and transition token regexes to accept `!`.
- Preserve `!` through multi-swara raaga resolution.
- Add pair detection and validation helpers.
- Add recognition and strength controls.
- Route marked playback through SCAMP.
- Build sphuritam pitch/volume envelopes.
- Remove `!` during spreadsheet cleaning.

### `carnatic/cparser.py`

- Accept `!` as a swara ornament.
- Add a raaga-aware sphuritam envelope helper.
- Preserve total duration.
- Keep `~` kampitam behavior unchanged.

### `carnatic/ctab_parser.py`

- Add optional metadata defaults.
- Preserve marked tokens during CTAB/CMN conversion.
- Validate recognition and strength settings.

### `carnatic/lessons.py`

- Add optional sphuritam annotation to Jantai Varisai output.
- Do not change other lesson types.
- Preserve legacy output by default.

## Backward compatibility

- Automatic Jantai recognition is off by default.
- Existing notes without `!` sound exactly as before.
- Existing `~` kampitam notation is unchanged.
- CTAB files require no migration.
- Single and multi-swara cells remain valid.
- Jantai generation changes only when explicitly requested.
- CSV and XLSX structure remains unchanged.

## Implementation phases

### Phase 1: notation and persistence

- Confirm the `!` marker.
- Extend tokenization, resolution, CTAB, and CMN round trips.
- Add pair detection and validation.
- Add editor controls and metadata.

### Phase 2: playback

- Add the raaga-aware approach calculation.
- Implement SCAMP pitch and accent envelopes.
- Route marked scores through SCAMP.
- Tune strength levels using listening tests.

### Phase 3: lessons and export

- Annotate generated Jantai lessons when requested.
- Strip sphuritam notation during spreadsheet export.
- Update user documentation.

## Test plan

### Tokenization

- `SS!`
- `R1R1!`
- `G G!`
- Upper- and lower-octave pairs
- Multiple pairs in one cell
- Mixed explicit and automatic markers
- Existing `~` kampitam tokens
- Invalid `~!`, `!!`, and punctuation markers

### Pair detection

- Identical resolved swaras are paired.
- Different swaras are not paired.
- Different octaves are not paired.
- Already-marked pairs are not double-marked.
- Recognition does not cross cell boundaries.
- Direction-aware raaga resolution occurs before comparison.

### Timing

- Sphuritam keeps the original token duration.
- Two swaras in one cell still consume two slots.
- Comma and semicolon durations remain correct.
- Playback highlights remain synchronized.
- Percussion duration is unchanged.

### Playback

- Second note receives an audible approach and accent.
- The approach uses a valid lower raaga swara.
- Strength levels are distinguishable without clipping.
- Pause, resume, stop, and replay work.
- Scores without sphuritam remain unchanged.

### Persistence and interoperability

- CTAB save/open preserves `!` and metadata.
- Copy/paste preserves markers.
- CMN round trip preserves markers.
- CSV/XLSX removes `!` only from exported values.
- Existing files load with recognition disabled.

## Out of scope for version 1

- Pratyahatam and other Jantai articulations
- Combining kampitam and sphuritam on one token
- Automatic pair recognition across cell or row boundaries
- Instrument-specific physical performance models
- Sphuritam on non-repeated phrases without an explicit marker
- Automatic conversion of every repeated note in existing compositions

## Review decisions

Please confirm these points before implementation:

1. Use `!` as the plain-text sphuritam marker.
2. Automatic Jantai recognition is opt-in and limited to pairs within one cell.
3. Explicit `!` remains valid even when automatic recognition is off.
4. Sphuritam uses a short raaga-aware lower approach plus target accent, not
   volume alone.
5. Scores containing `!` use SCAMP playback in version 1.
6. `~` kampitam and `!` sphuritam cannot be combined on one token initially.
7. Spreadsheet export removes `!` along with other gamaka notation.
8. Jantai lesson generation adds markers only when explicitly requested.
9. Mayamalavagowla and Adi tala are preset defaults, not restrictions.
