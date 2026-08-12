# antibody developability data from patents via LLMs

Extracts antibody thermal-stability measurements (Tm) from patent full text and
links them to protein sequences.

A patent reports a melting temperature for a named clone. Each clone has an alias name that is used in these assays. These clones are linked to `SEQ ID NO` used internally in the patent. These `SEQ ID NO` can be linked to amino acid sequences using EMBL-EBI's patent archive. Joining these gives `(sequence, Tm, conditions)` with verbatim source quotes.

## Pipeline

```
EBI sequences (46,453 US patents)
  └─ pull_html.py ────→ data/raw/fulltext_html.parquet   20,484 patents, $1.13
       └─ run_prototype.py
            ├─ whole document → one LLM call per patent → measurements
            └─ join on (patent, seq_id) → training rows
```

| script | scale | output |
| --- | --- | --- |
| `pull_html.py` | $1.13, once | `data/raw/fulltext_html.parquet` |
| `run_prototype.py` | ~40M tokens per 500 patents, ~7 min | `measurements_html.parquet`, `training_html.parquet` |

## Results for 500 patents

There is heterogeneity between runs even with `temperature=0`:

```
                        run A    run B
thermal measurements      282      426
grounded                  255      375     quote found verbatim in the patent
+ resolved sequence     51.0%    61.9%
+ method + pH/buffer    35.3%    22.7%     <- trainable share
+ transition            18.0%    12.3%
```

**Trainable share is roughly 20-35%.** `temperature=0` reduces run-to-run variation but does not remove it, so later runs will need to coalesce across multiple trials.

Every value carries the sentence it came from, and that quote is checked
against the source document; ~10% fail and are dropped.

## Modules

| module | what |
| --- | --- |
| `bq.py` | BigQuery: dry-run price, byte budget, manifest, read-only output |
| `ebi.py` | 1.81M patent-linked protein sequences |
| `prompt.py` | system prompt |
| `schema.py` | the `Measurement` model; field descriptions are prompt text |
| `llm.py` | Gemini clients, retry, concurrency; one call per patent |
| `manifest.py`, `paths.py` | provenance, file locations |

## Setup

```
uv sync
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```


## Verifying a value

`verbatim` holds the source sentence for every measurement, so any row can be
checked against the patent with a substring test.
