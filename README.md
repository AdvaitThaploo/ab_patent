# ab_patent

Extracts antibody thermal-stability measurements (Tm) from patent full text and
links them to protein sequences.

A patent reports a melting temperature for a named clone; the clone cites a
`SEQ ID NO`; the sequence itself lives in EMBL-EBI's patent archive. Joining
those gives `(sequence, Tm, conditions)` rows with a verbatim source quote.

## Pipeline

```
EBI sequences (46,453 US patents)
  └─ pull_html.py ────→ data/raw/fulltext_html.parquet   20,484 patents, $1.13
       └─ run_prototype.py
            ├─ whole document → one LLM call per patent → measurements
            └─ join on (patent, seq_id) → training rows
```

Two scripts, no notebooks. Whole documents go to the model: no keyword
windowing, no chunking. Gemini's context window fits a patent, and at 500
patents the token saving from any retrieval scheme is not worth the recall it
puts at risk -- keyword windowing silently lost tables twice during
development, because patents write Tm as `T<sub>m</sub>`.

| script | scale | output |
| --- | --- | --- |
| `pull_html.py` | $1.13, once | `data/raw/fulltext_html.parquet` |
| `run_prototype.py` | ~40M tokens per 500 patents, ~7 min | `measurements_html.parquet`, `training_html.parquet` |

## Results, 500 patents

Two runs, identical input, same seed, `temperature=0`:

```
                        run A    run B
thermal measurements      282      426
grounded                  255      375     quote found verbatim in the patent
+ resolved sequence     51.0%    61.9%
+ method + pH/buffer    35.3%    22.7%     <- trainable share
+ transition            18.0%    12.3%
```

A row is usable only with a sequence *and* the conditions that make it
comparable: the same antibody differs by ~8 C between pH 4.5 and pH 7.5, which
is most of the useful range across different antibodies.

**The trainable share is roughly 20-35%, and a single run cannot narrow it
further.** `temperature=0` reduces run-to-run variation but does not remove it,
and the spread here is wide enough to swallow any conclusion drawn from one
run. Average several runs, or raise the sample size, before treating this
number as a decision input.

Every value carries the sentence it came from, and that quote is checked
against the source document; ~10% fail and are dropped.

## Modules

| module | what |
| --- | --- |
| `bq.py` | BigQuery behind a cost gate: dry-run price, byte budget, manifest, read-only output |
| `ebi.py` | 1.81M patent protein sequences, keyed `(patent, seq_id)` |
| `prompt.py` | the system prompt — the domain knowledge lives here |
| `schema.py` | the `Measurement` model; field descriptions are prompt text |
| `llm.py` | Gemini/Anthropic clients, retry, concurrency; one call per patent |
| `manifest.py`, `paths.py` | provenance, file locations |

## Setup

```
uv sync
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

ADC is a refresh token on disk — one-time setup, not per-session.
`ABDEV_GCP_PROJECT` overrides the project.

## Cost control

`patents-public-data.patents.publications` is unpartitioned. **A `WHERE` clause
and a `LIMIT` do not reduce bytes scanned** — referencing a description column
scans it across all ~150M publications and bills you regardless of how many rows
return. Pulling 200 patents and pulling 46,453 cost the same. Pull everything,
once.

Every query goes through `bq.fetch` / `bq.fetch_stream`, which price a free dry
run first and refuse to execute over the byte budget. Results are written
read-only with a manifest recording the SQL, job ID, bytes billed, row count,
and checksum, so a paid pull cannot be silently overwritten.

## Archive

`../ab_patent_archive/from_ab_patent/` holds what this pipeline no longer uses:
the 18-property taxonomy, two retrieval strategies (keyword windowing and
structural table extraction), PLAbDab seeding, the earlier notebooks, and the
deck tooling. The retrieval modules become relevant again only at full scale,
where whole-document extraction across 20,484 patents runs to ~1.6B tokens.

## Verifying a value

`verbatim` holds the source sentence for every measurement, so any row can be
checked against the patent with a substring test -- no second model, no
judgement. That check caught three separate analysis bugs during development
and is now run as a pipeline stage.
