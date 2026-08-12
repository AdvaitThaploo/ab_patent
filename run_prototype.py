"""Extract Tm measurements from whole patents and count the trainable rows.

A row is trainable when it has a resolved sequence and the conditions that make
it comparable across patents. That count, as a share of measured rows, is the
number this project turns on.
"""

import re
import sys
import time

import polars as pl

sys.path.insert(0, "src")
from abdev import ebi, llm, paths

N_PATENTS = 500
SEED = 0
MAX_CHARS = 700_000  # fits the context window; p99 of description length
WORKERS = 20

INLINE = re.compile(r"</?(sub|sup|b|i)>")  # table headers write Tm as T<sub>m</sub>
TAGS = re.compile(r"<[^>]+>")


def flatten(s: str) -> str:
    """Tag-free, whitespace-normalised text, for comparing a quote to its source."""
    return " ".join(TAGS.sub(" ", s or "").split()).lower()


df = pl.read_parquet(paths.HTML).sample(N_PATENTS, seed=SEED)
texts = [INLINE.sub("", h)[:MAX_CHARS] for h in df["html"]]
print(f"{len(df)} patents, ~{sum(len(t) for t in texts) // 4:,} tokens")

cl = llm.client()
t0 = time.time()
rows = llm.extract_batch(cl, df["patent"].to_list(), texts, workers=WORKERS)
res = pl.DataFrame([r for b in rows for r in b], infer_schema_length=None)
res.write_parquet(paths.MEASUREMENTS)
print(f"{len(res)} rows in {time.time() - t0:.0f}s")

if res.is_empty():
    sys.exit("no measurements returned")

ok = res.filter(pl.col("error").is_null()) if "error" in res.columns else res
measured = ok.filter((pl.col("value_type") == "measured") & pl.col("value").is_not_null())
thermal = measured.filter(pl.col("property") == "thermal_stability")

# Every value carries the sentence it came from. Checking that quote against the
# patent is deterministic and free, and catches values the model composed rather
# than read. Rows that fail are dropped, not reported.
source = {p: flatten(t) for p, t in zip(df["patent"], texts)}
grounded = thermal.filter(
    pl.struct("patent", "verbatim")
    .map_elements(lambda r: flatten(r["verbatim"]) in source.get(r["patent"], ""),
                  return_dtype=pl.Boolean)
)
print(f"thermal {len(thermal)}  grounded {len(grounded)}  patents {grounded['patent'].n_unique()}")

# Sequences: join on (patent, seq_id); numbering is local to a patent. resolve()
# emits one row per (measurement, sequence), so count measurements by id.
grounded = grounded.with_row_index("mid")
linked = ebi.resolve(grounded)
linked.write_parquet(paths.TRAINING)

# A patent often states the buffer ("PBS", "20 mM histidine") and not its pH.
# Either identifies the condition.
f = linked.with_columns(
    method=pl.col("assay").struct.field("method"),
    ph=pl.col("conditions").struct.field("ph"),
    buffer=pl.col("conditions").struct.field("buffer"),
)
has_cond = pl.col("method").is_not_null() & (
    pl.col("ph").is_not_null() | pl.col("buffer").is_not_null()
)
uniq = lambda d: d["mid"].n_unique()
tiers = {
    "measured, grounded": len(grounded),
    "+ sequence": uniq(f),
    "+ method + pH/buffer": uniq(f.filter(has_cond)),
    "+ transition": uniq(f.filter(has_cond & pl.col("transition").is_not_null())),
}
print()
for name, n in tiers.items():
    print(f"{name:22} {n:5}  {100 * n / max(len(grounded), 1):5.1f}%")
