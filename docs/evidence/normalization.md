# Evidence text normalization policy

Owner task: `v1-e03-t01-text-normalization`. Implementation:
[`debate_core.evidence.normalization`](../../packages/debate_core/src/debate_core/evidence/normalization.py).
Architecture: proposal §8 steps 2 and 5, [ADR-0006](../adr/0006-exact-source-evidence-verification.md).

This page is the contract for the text that evidence comes from. When a source is retrieved, its
extracted text goes through `normalize(text, version)` once. Everything downstream works on the
result: the normalized-text SHA-256 (`v1-e03-t02`), the offsets and paragraph IDs a card's
quotation is cut at (`v1-e03-t03`), and the exact comparison the verifier makes (`v1-e03-t04`).
A stored offset or hash only means something together with the rules that produced it, so the
rules are frozen per version and every version stays callable.

## Versions

| `NORMALIZER_VERSION` | Status | Unicode database | Defined by |
|---|---|---|---|
| `evidence-normalizer-v1` | Current | 15.0.0 | This page |

**A released version is never edited.** Changing any rule below, including adding a code point
to a table, means a new version (`evidence-normalizer-v2`) with its own section on this page and
its own golden corpus. The v1 rules and their implementation stay in the module unchanged, so a
card verified under v1 can be re-verified under v1 forever. The golden test in
`packages/debate_core/tests/evidence/test_normalization_props.py` pins v1's output on the corpus
in `tests/fixtures/normalization/` and fails on any change to it.

`normalize` takes the version as a required argument. A caller that is re-verifying passes the
version recorded on the card, and a caller creating a snapshot passes `NORMALIZER_VERSION`. An
unknown version raises `UnknownNormalizerVersionError`, and it never falls back to the current
rules.

## What normalization is for, and what it must never do

This normalizer produces **the text that is quoted**. Its output is stored, displayed and cut into
cards, so it must preserve every word and every letter of the source. It may change only
whitespace and the code points listed on this page. It never lowercases, never folds quotes or
dashes, never expands ligatures and never rejoins hyphenated words.

It is not the card-fingerprint normalization in `debate_core.evidence.fingerprints`
(`v1-e31-t04`). That one applies NFKC, casefolds and folds quotes and dashes so that two cuttings
of one card hash alike, and its output is never stored or shown. The two normalizers have opposite
jobs. They share no code and must stay separate (see the task's forbidden list).

## The rules of `evidence-normalizer-v1`

Every code point of the input falls into exactly one of five classes. The tables are exhaustive:
a code point not listed in the first four tables is **content** and passes through the rules
unchanged, except for Unicode canonical normalization (rule 4).

### Rule 1: horizontal whitespace

| Code point | Name |
|---|---|
| U+0009 | CHARACTER TABULATION |
| U+0020 | SPACE |
| U+00A0 | NO-BREAK SPACE |
| U+1680 | OGHAM SPACE MARK |
| U+2000 | EN QUAD |
| U+2001 | EM QUAD |
| U+2002 | EN SPACE |
| U+2003 | EM SPACE |
| U+2004 | THREE-PER-EM SPACE |
| U+2005 | FOUR-PER-EM SPACE |
| U+2006 | SIX-PER-EM SPACE |
| U+2007 | FIGURE SPACE |
| U+2008 | PUNCTUATION SPACE |
| U+2009 | THIN SPACE |
| U+200A | HAIR SPACE |
| U+202F | NARROW NO-BREAK SPACE |
| U+205F | MEDIUM MATHEMATICAL SPACE |
| U+3000 | IDEOGRAPHIC SPACE |

These are the Unicode space separators (general category Zs) plus the tab. A run of them becomes
part of a whitespace gap (rule 5). The no-break spaces are included on purpose. Web and PDF
extraction produce them where the author typed an ordinary space, and a quotation cut across
`4&nbsp;percent` should match one cut across `4 percent`.

### Rule 2: line breaks

| Code point | Name | Note |
|---|---|---|
| U+000A | LINE FEED (LF) | |
| U+000B | LINE TABULATION (VT) | |
| U+000C | FORM FEED (FF) | PDF page breaks; usually mid-paragraph, so not a paragraph break |
| U+000D | CARRIAGE RETURN (CR) | CR immediately followed by LF counts as **one** line break |
| U+0085 | NEXT LINE (NEL) | |
| U+2028 | LINE SEPARATOR | |

### Rule 3: paragraph separator

| Code point | Name |
|---|---|
| U+2029 | PARAGRAPH SEPARATOR |

### Rule 4: removed invisible characters

| Code point | Name | Why it is removed |
|---|---|---|
| U+00AD | SOFT HYPHEN | Marks a place a word *may* break; PDF extraction leaves it inside words (`eco&shy;nomic`) |
| U+200B | ZERO WIDTH SPACE | Invisible break opportunity inserted by CMSs and web extractors |
| U+2060 | WORD JOINER | Invisible; the non-deprecated form of U+FEFF |
| U+FEFF | ZERO WIDTH NO-BREAK SPACE | The byte-order mark, which survives decoding at the start of files and at concatenation seams |

Each of these is deleted. Deleting one joins the characters on either side into one piece of
content (so `eco&shy;nomic` becomes `economic`), and a deleted character never separates words.
When a removed character sits between a base letter and a combining mark, the two are joined and
then composed by rule 5.

### Rule 5: Unicode canonical normalization (NFC)

After rule 4 each run of content (the text between whitespace gaps) is put in Unicode
Normalization Form C, as defined by the Unicode 15.0.0 character database. NFC is canonical
equivalence only: the result is the same letters, encoded one standard way. Two things happen.

* **Replacement.** 1,120 code points never survive NFC: singletons (U+212B ANGSTROM SIGN becomes
  U+00C5), composition exclusions and characters with non-starter decompositions. They are
  replaced by their canonical equivalents wherever they occur. The full list is in the appendix
  table "Code points NFC always replaces".
* **Composition and reordering.** A base character followed by combining marks is composed where
  Unicode defines a precomposed character (`e` + U+0301 becomes `é`), and runs of combining marks
  are put in canonical order. The 111 code points that can be absorbed into a preceding character
  are listed in the appendix table "Code points NFC may compose with a preceding character".

NFKC, the compatibility form, is **not** applied. It would rewrite ligatures (`ﬁ`), superscripts,
fractions and full-width letters, which changes what the source visibly says.

### Rule 6: whitespace gaps and paragraph breaks

A **gap** is a maximal run of code points from rules 1-4. Gaps are replaced as follows:

1. A gap at the very start or end of the text is deleted.
2. A gap made only of rule-4 characters is deleted, and the content on either side is joined.
3. A gap that contains U+2029, or contains two or more line breaks (CR LF counting as one), is a
   **paragraph break** and becomes exactly `\n\n` (two U+000A).
4. Any other gap becomes exactly one U+0020 SPACE. This covers runs of spaces, tabs and no-break
   spaces, and single line breaks inside a paragraph (hard-wrapped lines).

Item 3 is the same as saying that a paragraph ends at a blank line, meaning a line holding nothing
but whitespace and invisible characters. A single line break is never a paragraph break, because
PDF extraction and hard-wrapped plain text put one at the end of every line.

### Paragraphs and paragraph IDs

The normalized text is split on `\n\n`. The paragraphs are numbered in order from 1, and each
gets the ID `p` followed by its number padded to four digits (`p0001`, `p0002`, ...,
`p9999`, `p10000`). The model references paragraphs by these IDs and never rewrites their text.

IDs depend only on how many paragraph breaks come before a paragraph. Whitespace edits inside a
paragraph therefore never change any ID or the paragraph count: extra spaces, tabs, no-break
spaces, a line break that does not create a blank line, or whitespace at a paragraph's edges.
Adding or removing a blank line does change the count, because a blank line is a paragraph break.
Text that is empty, or only whitespace and invisible characters, normalizes to `""` with no
paragraphs.

### Offset map

`NormalizedText` carries an offset map between the raw text (the `str` given to `normalize`) and
the normalized text. Offsets are Python string indices, which count Unicode code points (not
bytes and not UTF-16 units). The map is a sequence of aligned segments covering both texts:

* an **exact** segment is copied unchanged, character for character, so any position inside it
  maps one to one;
* a **replaced** segment is a raw run that became something else: a whitespace gap (becoming
  `" "`, `"\n\n"` or nothing), a removed character, or a content run that NFC changed. It maps as
  a unit and cannot be split.

`to_raw_range(start, end)` returns the smallest raw range whose characters produced normalized
`[start, end)`. A range edge inside a replaced segment widens to take in the whole segment, and a
deleted raw character just outside the range is left out. `to_normalized_range(start, end)` is the
reverse, and it widens the same way. Mapping a range to the other text and back again never
loses a character. An empty range inside a replaced segment has no finer position to map to and
lands at the segment's start.

## What is deliberately not changed

Every entry below was considered and rejected, because each would change what a reader sees in
the quotation.

| Phenomenon | Examples | Decision | Reason |
|---|---|---|---|
| Curly quotes and apostrophes | U+2018, U+2019, U+201C, U+201D, U+2032 | Kept | Quotation marks are part of the quoted text. Matching across quote styles is the fingerprint normalizer's job |
| Dashes and hyphens | U+002D, U+2010-U+2015, U+2212 | Kept | An em dash and a hyphen are different punctuation |
| Hyphen at a line end | `eco-` LF `nomic` | Line break becomes a space: `eco- nomic` | Rejoining would need a dictionary to tell `eco-nomic` from `well-known`, and guessing wrong alters a word |
| Ligatures | U+FB00-U+FB06 (`ﬁ`, `ﬂ`) | Kept | Only NFKC expands them. Search and matching should fold them; quoted text should not |
| Letter case | | Kept | No `lower()`, `casefold()` or `upper()` is applied to anything |
| Zero-width joiner and non-joiner | U+200C, U+200D | Kept | They carry meaning in Persian, Indic scripts and emoji sequences |
| Bidirectional controls | U+061C, U+200E, U+200F, U+202A-U+202E, U+2066-U+2069 | Kept | Removing them can reorder how right-to-left text displays |
| Other controls and format characters | U+0000-U+0008, U+001C-U+001F, U+034F, U+180E, U+2061-U+2064 | Kept | Not whitespace by this policy's explicit tables, whatever `str.isspace()` says |
| Private-use characters, noncharacters, U+FFFD | | Kept | Passed through; the extractor decides what they were |

## Determinism

The normalizer does no I/O and uses no randomness, locale, environment variable or clock. Its
character classes are the explicit tables above, never `str.isspace()`, `str.splitlines()` or a
regular-expression `\s`, whose membership follows the running Python's Unicode version. Nothing in
it iterates a set or dict in a way that can reach the output.

The one external dependency is the Unicode character database behind `unicodedata.normalize`.
**v1 is pinned to Unicode 15.0.0**, the database of every Python 3.12 release (the repository's
`requires-python` and `.python-version`). `normalize` checks `unicodedata.unidata_version` on
every call and raises `UnicodeDatabaseMismatchError` rather than run v1 under a different
database. Unicode's normalization stability policy means NFC of characters assigned in 15.0 can
never change. Characters assigned later can, though: under 15.0 they are unassigned and pass
through NFC unchanged, while a newer database may decompose them. Moving the project to a Python
with a newer Unicode database is therefore a deliberate step, not a side effect of an upgrade.
Someone has to check that v1's output is unchanged on everything assigned in 15.0, and handle the
newer characters with either a new normalizer version or an explicit v1 carve-out.

Input must be valid Unicode text. A string containing a lone surrogate (U+D800-U+DFFF), which
cannot be encoded as UTF-8 and so cannot be hashed by `v1-e03-t02`, raises `InvalidTextError`.

## Guarantees, and the tests that hold them

| Guarantee | Test |
|---|---|
| `normalize(normalize(x).text) == normalize(x)` for any Unicode `x`, and repeated calls agree | hypothesis, `test_normalization_props.py` |
| The output is NFC and contains no rule 1-4 code point except U+0020 and U+000A | hypothesis |
| Only whitespace and the listed code points change: removing all whitespace and rule-4 characters from input and output leaves text that is canonically equivalent (equal after NFC) | hypothesis |
| Whitespace edits inside a paragraph change no paragraph ID and not the count | hypothesis |
| `to_raw_range` of any normalized range returns raw text with the same characters | hypothesis |
| v1's output on the invented golden corpus is exactly the hand-written expectation | golden test, `tests/fixtures/normalization/` |
| The tables on this page match the implementation's tables and the pinned Unicode database | `test_normalization.py` |

## Appendix: Unicode 15.0.0 code points NFC transforms

Both tables were produced from Python 3.12's `unicodedata` (Unicode 15.0.0) and are checked
against it by `test_normalization.py`, which fails if either table and the database disagree.
They list Unicode's data rather than choices of this policy: they are here so that the page names
every code point the normalizer can change.

### Code points NFC always replaces

A code point in this table never appears in normalized text. It is replaced by its canonical
equivalent. 1,120 code points in 73 ranges.

| Range | Count | First | Last |
|---|---:|---|---|
| U+0340–U+0341 | 2 | COMBINING GRAVE TONE MARK | COMBINING ACUTE TONE MARK |
| U+0343–U+0344 | 2 | COMBINING GREEK KORONIS | COMBINING GREEK DIALYTIKA TONOS |
| U+0374 | 1 | GREEK NUMERAL SIGN |  |
| U+037E | 1 | GREEK QUESTION MARK |  |
| U+0387 | 1 | GREEK ANO TELEIA |  |
| U+0958–U+095F | 8 | DEVANAGARI LETTER QA | DEVANAGARI LETTER YYA |
| U+09DC–U+09DD | 2 | BENGALI LETTER RRA | BENGALI LETTER RHA |
| U+09DF | 1 | BENGALI LETTER YYA |  |
| U+0A33 | 1 | GURMUKHI LETTER LLA |  |
| U+0A36 | 1 | GURMUKHI LETTER SHA |  |
| U+0A59–U+0A5B | 3 | GURMUKHI LETTER KHHA | GURMUKHI LETTER ZA |
| U+0A5E | 1 | GURMUKHI LETTER FA |  |
| U+0B5C–U+0B5D | 2 | ORIYA LETTER RRA | ORIYA LETTER RHA |
| U+0F43 | 1 | TIBETAN LETTER GHA |  |
| U+0F4D | 1 | TIBETAN LETTER DDHA |  |
| U+0F52 | 1 | TIBETAN LETTER DHA |  |
| U+0F57 | 1 | TIBETAN LETTER BHA |  |
| U+0F5C | 1 | TIBETAN LETTER DZHA |  |
| U+0F69 | 1 | TIBETAN LETTER KSSA |  |
| U+0F73 | 1 | TIBETAN VOWEL SIGN II |  |
| U+0F75–U+0F76 | 2 | TIBETAN VOWEL SIGN UU | TIBETAN VOWEL SIGN VOCALIC R |
| U+0F78 | 1 | TIBETAN VOWEL SIGN VOCALIC L |  |
| U+0F81 | 1 | TIBETAN VOWEL SIGN REVERSED II |  |
| U+0F93 | 1 | TIBETAN SUBJOINED LETTER GHA |  |
| U+0F9D | 1 | TIBETAN SUBJOINED LETTER DDHA |  |
| U+0FA2 | 1 | TIBETAN SUBJOINED LETTER DHA |  |
| U+0FA7 | 1 | TIBETAN SUBJOINED LETTER BHA |  |
| U+0FAC | 1 | TIBETAN SUBJOINED LETTER DZHA |  |
| U+0FB9 | 1 | TIBETAN SUBJOINED LETTER KSSA |  |
| U+1F71 | 1 | GREEK SMALL LETTER ALPHA WITH OXIA |  |
| U+1F73 | 1 | GREEK SMALL LETTER EPSILON WITH OXIA |  |
| U+1F75 | 1 | GREEK SMALL LETTER ETA WITH OXIA |  |
| U+1F77 | 1 | GREEK SMALL LETTER IOTA WITH OXIA |  |
| U+1F79 | 1 | GREEK SMALL LETTER OMICRON WITH OXIA |  |
| U+1F7B | 1 | GREEK SMALL LETTER UPSILON WITH OXIA |  |
| U+1F7D | 1 | GREEK SMALL LETTER OMEGA WITH OXIA |  |
| U+1FBB | 1 | GREEK CAPITAL LETTER ALPHA WITH OXIA |  |
| U+1FBE | 1 | GREEK PROSGEGRAMMENI |  |
| U+1FC9 | 1 | GREEK CAPITAL LETTER EPSILON WITH OXIA |  |
| U+1FCB | 1 | GREEK CAPITAL LETTER ETA WITH OXIA |  |
| U+1FD3 | 1 | GREEK SMALL LETTER IOTA WITH DIALYTIKA AND OXIA |  |
| U+1FDB | 1 | GREEK CAPITAL LETTER IOTA WITH OXIA |  |
| U+1FE3 | 1 | GREEK SMALL LETTER UPSILON WITH DIALYTIKA AND OXIA |  |
| U+1FEB | 1 | GREEK CAPITAL LETTER UPSILON WITH OXIA |  |
| U+1FEE–U+1FEF | 2 | GREEK DIALYTIKA AND OXIA | GREEK VARIA |
| U+1FF9 | 1 | GREEK CAPITAL LETTER OMICRON WITH OXIA |  |
| U+1FFB | 1 | GREEK CAPITAL LETTER OMEGA WITH OXIA |  |
| U+1FFD | 1 | GREEK OXIA |  |
| U+2000–U+2001 | 2 | EN QUAD | EM QUAD |
| U+2126 | 1 | OHM SIGN |  |
| U+212A–U+212B | 2 | KELVIN SIGN | ANGSTROM SIGN |
| U+2329–U+232A | 2 | LEFT-POINTING ANGLE BRACKET | RIGHT-POINTING ANGLE BRACKET |
| U+2ADC | 1 | FORKING |  |
| U+F900–U+FA0D | 270 | CJK COMPATIBILITY IDEOGRAPH-F900 | CJK COMPATIBILITY IDEOGRAPH-FA0D |
| U+FA10 | 1 | CJK COMPATIBILITY IDEOGRAPH-FA10 |  |
| U+FA12 | 1 | CJK COMPATIBILITY IDEOGRAPH-FA12 |  |
| U+FA15–U+FA1E | 10 | CJK COMPATIBILITY IDEOGRAPH-FA15 | CJK COMPATIBILITY IDEOGRAPH-FA1E |
| U+FA20 | 1 | CJK COMPATIBILITY IDEOGRAPH-FA20 |  |
| U+FA22 | 1 | CJK COMPATIBILITY IDEOGRAPH-FA22 |  |
| U+FA25–U+FA26 | 2 | CJK COMPATIBILITY IDEOGRAPH-FA25 | CJK COMPATIBILITY IDEOGRAPH-FA26 |
| U+FA2A–U+FA6D | 68 | CJK COMPATIBILITY IDEOGRAPH-FA2A | CJK COMPATIBILITY IDEOGRAPH-FA6D |
| U+FA70–U+FAD9 | 106 | CJK COMPATIBILITY IDEOGRAPH-FA70 | CJK COMPATIBILITY IDEOGRAPH-FAD9 |
| U+FB1D | 1 | HEBREW LETTER YOD WITH HIRIQ |  |
| U+FB1F | 1 | HEBREW LIGATURE YIDDISH YOD YOD PATAH |  |
| U+FB2A–U+FB36 | 13 | HEBREW LETTER SHIN WITH SHIN DOT | HEBREW LETTER ZAYIN WITH DAGESH |
| U+FB38–U+FB3C | 5 | HEBREW LETTER TET WITH DAGESH | HEBREW LETTER LAMED WITH DAGESH |
| U+FB3E | 1 | HEBREW LETTER MEM WITH DAGESH |  |
| U+FB40–U+FB41 | 2 | HEBREW LETTER NUN WITH DAGESH | HEBREW LETTER SAMEKH WITH DAGESH |
| U+FB43–U+FB44 | 2 | HEBREW LETTER FINAL PE WITH DAGESH | HEBREW LETTER PE WITH DAGESH |
| U+FB46–U+FB4E | 9 | HEBREW LETTER TSADI WITH DAGESH | HEBREW LETTER PE WITH RAFE |
| U+1D15E–U+1D164 | 7 | MUSICAL SYMBOL HALF NOTE | MUSICAL SYMBOL ONE HUNDRED TWENTY-EIGHTH NOTE |
| U+1D1BB–U+1D1C0 | 6 | MUSICAL SYMBOL MINIMA | MUSICAL SYMBOL FUSA BLACK |
| U+2F800–U+2FA1D | 542 | CJK COMPATIBILITY IDEOGRAPH-2F800 | CJK COMPATIBILITY IDEOGRAPH-2FA1D |

### Code points NFC may compose with a preceding character

A code point in this table survives NFC unless it follows a character it composes with. In that
case the pair becomes one precomposed character (a Hangul jamo sequence becomes a syllable). 111
code points in 42 ranges.

| Range | Count | First | Last |
|---|---:|---|---|
| U+0300–U+0304 | 5 | COMBINING GRAVE ACCENT | COMBINING MACRON |
| U+0306–U+030C | 7 | COMBINING BREVE | COMBINING CARON |
| U+030F | 1 | COMBINING DOUBLE GRAVE ACCENT |  |
| U+0311 | 1 | COMBINING INVERTED BREVE |  |
| U+0313–U+0314 | 2 | COMBINING COMMA ABOVE | COMBINING REVERSED COMMA ABOVE |
| U+031B | 1 | COMBINING HORN |  |
| U+0323–U+0328 | 6 | COMBINING DOT BELOW | COMBINING OGONEK |
| U+032D–U+032E | 2 | COMBINING CIRCUMFLEX ACCENT BELOW | COMBINING BREVE BELOW |
| U+0330–U+0331 | 2 | COMBINING TILDE BELOW | COMBINING MACRON BELOW |
| U+0338 | 1 | COMBINING LONG SOLIDUS OVERLAY |  |
| U+0342 | 1 | COMBINING GREEK PERISPOMENI |  |
| U+0345 | 1 | COMBINING GREEK YPOGEGRAMMENI |  |
| U+0653–U+0655 | 3 | ARABIC MADDAH ABOVE | ARABIC HAMZA BELOW |
| U+093C | 1 | DEVANAGARI SIGN NUKTA |  |
| U+09BE | 1 | BENGALI VOWEL SIGN AA |  |
| U+09D7 | 1 | BENGALI AU LENGTH MARK |  |
| U+0B3E | 1 | ORIYA VOWEL SIGN AA |  |
| U+0B56–U+0B57 | 2 | ORIYA AI LENGTH MARK | ORIYA AU LENGTH MARK |
| U+0BBE | 1 | TAMIL VOWEL SIGN AA |  |
| U+0BD7 | 1 | TAMIL AU LENGTH MARK |  |
| U+0C56 | 1 | TELUGU AI LENGTH MARK |  |
| U+0CC2 | 1 | KANNADA VOWEL SIGN UU |  |
| U+0CD5–U+0CD6 | 2 | KANNADA LENGTH MARK | KANNADA AI LENGTH MARK |
| U+0D3E | 1 | MALAYALAM VOWEL SIGN AA |  |
| U+0D57 | 1 | MALAYALAM AU LENGTH MARK |  |
| U+0DCA | 1 | SINHALA SIGN AL-LAKUNA |  |
| U+0DCF | 1 | SINHALA VOWEL SIGN AELA-PILLA |  |
| U+0DDF | 1 | SINHALA VOWEL SIGN GAYANUKITTA |  |
| U+102E | 1 | MYANMAR VOWEL SIGN II |  |
| U+1161–U+1175 | 21 | HANGUL JUNGSEONG A | HANGUL JUNGSEONG I |
| U+11A8–U+11C2 | 27 | HANGUL JONGSEONG KIYEOK | HANGUL JONGSEONG HIEUH |
| U+1B35 | 1 | BALINESE VOWEL SIGN TEDUNG |  |
| U+3099–U+309A | 2 | COMBINING KATAKANA-HIRAGANA VOICED SOUND MARK | COMBINING KATAKANA-HIRAGANA SEMI-VOICED SOUND MARK |
| U+110BA | 1 | KAITHI SIGN NUKTA |  |
| U+11127 | 1 | CHAKMA VOWEL SIGN A |  |
| U+1133E | 1 | GRANTHA VOWEL SIGN AA |  |
| U+11357 | 1 | GRANTHA AU LENGTH MARK |  |
| U+114B0 | 1 | TIRHUTA VOWEL SIGN AA |  |
| U+114BA | 1 | TIRHUTA VOWEL SIGN SHORT E |  |
| U+114BD | 1 | TIRHUTA VOWEL SIGN SHORT O |  |
| U+115AF | 1 | SIDDHAM VOWEL SIGN AA |  |
| U+11930 | 1 | DIVES AKURU VOWEL SIGN AA |  |
