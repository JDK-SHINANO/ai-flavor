# ai-flavor

[简体中文](README.md)

A rubric for Chinese "AI flavor": the texture that makes a text read as machine-written. It splits that texture into metrics you can count, entries you can look up, and diffs you can re-run.

233 lexicon entries. Nine register tiers, five rewrite levels, three defects and three fixes.

## What it is

The project grew out of [blader/humanizer](https://github.com/blader/humanizer) (34 English entries) and [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) (31 Chinese ones). Both checklists work. I used them for the better part of a year.

Three problems turned up that a checklist can't handle.

The first is that deletion doesn't finish the job. Checklist editing only subtracts: cross out the suspect word, drop the connective that isn't earning its place. You can cut the vocabulary to zero and end up with sentences more even than before. The blind test in upstream [issue #229](https://github.com/blader/humanizer/issues/229) is on record. AI vocabulary went 70→0 and typography 60→0, while "even rhythm" went 60→101 and "aphoristic ending" 38→61. What's left has no defects and no person in it.

The second: the same word can be a defect in one place and normal in another. Nominalization is ordinary in an academic paper and a defect in an essay. 总之 closes a government document and sours a personal one. A register-blind checklist can only take the most conservative reading, so it misfires everywhere.

The third is more practical. After the edit, there's no measure of whether it got better. You go by feel.

The register tiers, the comparison tool and the three defects are aimed at those three problems, one each.

### Three defects, three fixes

| Defect | What it is | Fix | Test |
|---|---|---|---|
| A. Hard-mapped hypotaxis | An English grammatical obligation dropped into a slot Chinese leaves optional | Correct the form | Departs from the Chinese default and buys no precision |
| B. Register collapse | One register for the whole text, wrong for the target genre | Set the register | Departs from the target tier's default, either high or low |
| C. Predictable structure | The reader can guess the shape of the next sentence | Break the rhythm | Low variance in sentence length, equal-length sections, predictable placement of punchlines |

The three defects are independent, each with its own fix. Treat them together and some will be missed.

Defect A has one precondition: whether the Europeanized form pays for itself. With a source text behind it (translation), it may be the price of fidelity, so the tolerance goes up one notch. When you are writing on your own and the form still comes out Europeanized, that is path inertia and gets treated as a defect.

Defect B runs both ways. An essay written like a government notice is a defect; a government notice written like a stand-up bit is also a defect. The fix is not to drag everything toward speech.

Defect C has the strongest evidence and the weakest fix. The distribution gap between human and AI text is well measured (sentence-length standard deviation differs by a factor of 1.37), but no intervention study shows that raising the variance makes a text read more human. Marked as unverified until one exists.

### Tiers and levels

Nine register tiers: R1 academic, R2 official document, R3 technical documentation, R4 news, R5 popular science, R6 social media, R7 literary essay, R8 personal letter, R9 translation polish. Each has its own defaults and hard constraints. The same entry carries a different severity depending on the tier it lands in.

Five rewrite levels: L0 reports without touching a character, L1 removes surface problems, L2 also repairs syntax, L3 changes paragraph structure, L4 rewrites. The further you go, the more a human needs to watch.

Audience and consequence count as well. If the text goes on file (a thesis, an official document, a contract), drop one level of force and touch only what is certain. A one-off message can be handled less carefully.

### Measurements

One rubric, three kinds of text:

| Text | Words | High-confidence hits | Note |
|---|---|---|---|
| AI-generated argumentative essay | 1076 | 7 | Textbook template voice |
| Human academic writing (one chapter) | 6744 | 0 | Over two hundred entries, no false positives |
| Official-document sample | — | 3 → 1 | After the tier downgrade, 抓手 and 闭环 count as leads |

Two further trials compare the old and new criteria, at 1270 and 1076 characters. The records are in `docs/research/contrast-trials-2026-10/`. First-round finding: XH alone beats ZH alone, and both beat running the two in sequence. Run in sequence, they strip qualifiers and claims along with the flagged items. The sample has not reached the planned 10–20 passages, so treat this as a preliminary read.

## How to use

```bash
# run from the repository root

# profile and scan
python3 src/af.py metrics 文件.md
python3 src/af.py scan 文件.md
python3 src/af.py scan --level 修辞 --min-conf high 文件.md
python3 src/af.py scan --register R2 公文.md     # entries legal in this tier drop to leads

# compare draft and revision: alerts when sentence-length SD or paragraph-range shrinks
python3 src/af.py check 原稿.md 改稿.md

# merge and validate the lexicon
python3 src/af.py lexicon
python3 src/af.py lexicon --check
```

The scripts produce evidence, not verdicts. They give line numbers, fragments and confidence. Deciding is your job.

Install as a Hermes skill:

```bash
rsync -a --exclude .git ./ ~/.hermes/skills/creative/ai-flavor/
```

## Layout

```
.
├── README.md
├── README.en.md
├── SKILL.md                    Skill entry: three defects, five-step workflow, tiers and presets
├── LICENSE
├── NOTICE                      Copyright notices for upstream MIT projects
├── src/                        af.py entry point plus scan, metrics, check, lexicon modules
├── docs/
│   ├── MIGRATION.md            Entry-by-entry against humanize's 93: inherited, rewritten, dropped
│   ├── 00-设计草案.md           Original design frame, superseded by research, kept for comparison
│   ├── references/             Six references: model, whitelist, tiers, fixes, evidence, failure modes
│   └── research/               Six studies (A–F), merged conclusions, brief, old-vs-new trials
├── assets/
│   └── lexicon/                233-entry main lexicon, four raw collection passes, merger, adjudication table
└── tests/                      Samples, five-level trials and results
```

## Requirements

Python 3.10 or newer. No hard third-party dependencies. With `jieba` installed, word segmentation is more accurate and matches the baseline; without it the scanner falls back to longest-match, estimates the word-count denominator at 1.704 characters per word, and adds a `warn` column.

```bash
sudo apt install python3-jieba
```

The scripts strip table rows, code blocks and frontmatter. Skip that and a whole table row is read as one sentence. In testing this pushed the maximum sentence length from 48 characters to 503 and ruined every metric.

## Scope

The criteria expire. The baseline models and corpora date from 2024–2026, and multipliers such as connective density and particle density shift as models are retrained. On the English side the em dash signal is already fading. Retest in a year or two.

The sampled corpus is mostly Q&A text. Extrapolating the multipliers to literary prose or technical documentation costs accuracy. The human baseline is the distribution of comparable corpora, not of all human writing; texts under a thousand characters should only be compared against short texts of the same kind.

## Acknowledgements

[blader/humanizer](https://github.com/blader/humanizer) (Siqi Chen, [@blader](https://github.com/blader)) and [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) (歸藏, [@op7418](https://github.com/op7418)) are where this started. Those two checklists turned "AI flavor" from an impression into something you can point at. `docs/MIGRATION.md` records, entry by entry, what was inherited, what was rewritten and what was left out.

Some entries come from Zhihu, WeChat public accounts and [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing). Most are folk observation, graded by strength of evidence; anything without empirical support is capped at mid.

## License

MIT. See [LICENSE](LICENSE). For lexicon entries and directory structure carried over from upstream, see [NOTICE](NOTICE).
