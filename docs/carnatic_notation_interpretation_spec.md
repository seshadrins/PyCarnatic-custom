# Carnatic Notation Interpretation Spec

## Purpose
This document captures the notation interpretation rules discussed so that a software program can read Carnatic notation strings and map them to the correct swaras, octave levels, and durations.

---

## 1. Basic Swara Symbols

The basic Carnatic swara symbols are:

- `S` = Shadjam
- `R` = Rishabham
- `G` = Gandharam
- `M` = Madhyamam
- `P` = Panchamam
- `D` = Dhaivatam
- `N` = Nishadam

These symbols usually appear in compositions and exercises.

---

## 2. Swarasthana Resolution

In actual notation for a song or lesson, the notation may show only `R`, `G`, `M`, `D`, `N` without specifying whether they are `R1`, `R2`, `R3`, etc.

The exact swarasthana must be inferred from the **raga**.

### Rule
If the raga is known, resolve each swara symbol using the raga’s arohanam and avarohanam.

### Example
If the raga is **Shankarabharanam**:
- `R` -> `R2`
- `G` -> `G3`
- `M` -> `M1`
- `D` -> `D2`
- `N` -> `N3`

If the raga is **Mayamalavagowla**:
- `R` -> `R1`
- `G` -> `G3`
- `M` -> `M1`
- `D` -> `D1`
- `N` -> `N3`

### Important Note
For a software player, arohanam and avarohanam may be sufficient to map plain notation to pitch positions.
For authentic musical rendering, gamakas and characteristic prayogas are also important, but those were not part of this discussion.

---

## 3. Octave / Sthayi Levels

A swara symbol may appear at different pitch levels.

### Notation discussed
- `s` = lower octave Sa (mandra sthayi)
- `S` = middle octave Sa (madhya sthayi)
- `^S` = upper octave Sa (tara sthayi)

This same pattern can be applied to other swaras:
- `r`, `g`, `m`, `p`, `d`, `n` -> lower octave
- `R`, `G`, `M`, `P`, `D`, `N` -> middle octave
- `^R`, `^G`, `^M`, `^P`, `^D`, `^N` -> upper octave

### Suggested program interpretation
Use an octave offset field:
- lowercase swara -> octave = -1
- uppercase swara -> octave = 0
- `^` prefixed swara -> octave = +1

### Example
- `s` -> Sa, lower octave
- `S` -> Sa, middle octave
- `^S` -> Sa, upper octave

---

## 4. Duration / Hold Markers

The notation may include symbols such as `,`, `;`, and `-` after a swara.

### Example discussed
`S R G , ; P-`

This should be interpreted as:
- `S` = play Sa
- `R` = play Ri
- `G , ;` = play Ga and sustain it for additional duration
- `P-` = play Pa and sustain it

### Meaning of symbols
A practical interpretation based on the discussion:

- `,` = extend the previous swara by 1 extra unit
- `;` = extend the previous swara further
- `-` = hold for 0.25 unit / sustain the current swara into the next unit

### Program-friendly rule
These symbols do **not** introduce a new swara.
They only modify the duration of the immediately preceding swara.

### Recommended default model
Treat each swara as having a base duration of 1 unit.
Then apply duration modifiers.

Suggested default interpretation:
- plain swara = duration 1
- `,` = add 1 unit
- `;` = add 2 or more units depending on the notation system
- `-` = sustain current swara by 0.25 extra unit

### Conservative implementation guidance
Because exact duration meaning can vary by notation style or teacher, the software should allow configuration of these symbols.

Suggested config structure:

```json
{
  "base_duration": 1,
  "duration_modifiers": {
    ",": 1,
    ";": 2,
    "-": 1
  }
}
```

If the notation source uses a different convention, these values can be changed without changing the parser.

---

## 5. Interpretation of `R1`, `R2`, `R3`

When explicitly written, the three Rishabham variants are:

- `R1` = Shuddha Rishabham
- `R2` = Chatushruti Rishabham
- `R3` = Shatsruti Rishabham

These represent three pitch positions for Ri.

For parsing purposes, if the notation explicitly includes `R1`, `R2`, `R3`, the program should use those values directly instead of inferring from the raga.

The same principle applies to:
- `G1`, `G2`, `G3`
- `M1`, `M2`
- `D1`, `D2`, `D3`
- `N1`, `N2`, `N3`

---

## 6. Default Resolution Strategy

When parsing notation, use the following order:

### Case 1: Explicit swarasthana present
If the notation contains symbols like `R1`, `G3`, `D2`, use them directly.

### Case 2: Only plain swara letters present
If the notation contains only `R`, `G`, `M`, `D`, `N`, then:
1. identify the raga
2. resolve the corresponding swarasthana from the raga

### Case 3: No raga information available
If the notation contains plain `R`, `G`, `M`, `D`, `N` but no raga metadata, the parser cannot determine the exact pitch reliably.
In such a case the program should either:
- raise an error, or
- mark the swara as unresolved

---

## 7. Example Parsing

### Input
`S R G , ; P-`

### Parsed meaning
- `S` -> Sa, middle octave, duration 1
- `R` -> Ri, middle octave, duration 1
- `G,;` -> Ga, middle octave, duration base + modifiers
- `P-` -> Pa, middle octave, duration base + sustain

