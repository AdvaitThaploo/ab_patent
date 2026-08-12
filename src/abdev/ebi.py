"""EMBL-EBI patent protein sequences, USPTO division.

The sequence source for the pipeline. Records are keyed by (patent, seq_id),
which is the key patent text uses when citing a sequence. SEQ ID numbering is
local to each patent, so both fields are required to identify a sequence.

Coverage: 46,453 US patents, against 8,247 in PLAbDab. PLAbDab is derived from
this source but retains only records it could pair into VH/VL; it is used here
for pairing and diversity comparison, not for sequence lookup.
"""

from __future__ import annotations

import gzip
import re
import subprocess
from pathlib import Path

import polars as pl

from . import paths

URL = "https://ftp.ebi.ac.uk/pub/databases/patentdata/uspto_prt.dat.gz"
DE = re.compile(r"^DE   Sequence (\d+) from patent ([A-Z]{2}) ?(\d+)", re.M)
VDOM = (90, 200)  # amino acid length range for a VH or VL domain


def stream(dest: Path = paths.EBI, vdom_only: bool = True) -> Path:
    """Download, decompress, and parse the source file without writing it to disk.

    The source is 3.3 GB compressed. Data streams through curl and gzip
    directly into the parser. Runtime is approximately 40 minutes.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["curl", "-sSL", URL], stdout=subprocess.PIPE)
    rows, seq_id, patent, seq, in_seq, n = [], None, None, [], False, 0
    with gzip.open(proc.stdout, "rt", errors="replace") as fh:
        for line in fh:
            if line.startswith("DE   Sequence "):
                m = DE.match(line)
                if m:
                    seq_id, patent = int(m[1]), f"{m[2]}-{m[3]}"
            elif line.startswith("SQ   "):
                in_seq, seq = True, []
            elif line.startswith("//"):
                if patent and seq:
                    s = "".join(seq)
                    n += 1
                    if not vdom_only or VDOM[0] <= len(s) <= VDOM[1]:
                        rows.append((patent, seq_id, s))
                seq_id, patent, seq, in_seq = None, None, [], False
            elif in_seq:
                seq.append(re.sub(r"[^A-Z]", "", line.upper()))
    df = pl.DataFrame(rows, schema=["patent", "seq_id", "sequence"], orient="row")
    df.write_parquet(dest)
    print(f"parsed {n:,} records, kept {df.height:,} ({df['patent'].n_unique():,} patents)")
    return dest


def load() -> pl.DataFrame:
    """Return the parsed sequence table. Columns: patent, seq_id, sequence."""
    if not paths.EBI.exists():
        stream()
    return pl.read_parquet(paths.EBI)


def patents() -> pl.Series:
    """Return the patent IDs that have at least one V-domain-length sequence."""
    return load()["patent"].unique()


def resolve(measurements: pl.DataFrame) -> pl.DataFrame:
    """Join measurements to sequences on (patent, seq_id).

    Input must have a `seq_ids` list column. Returns one row per
    (measurement, sequence) pair, adding seq_id and sequence columns. Rows
    whose SEQ IDs are not in the sequence table are dropped: those reference
    non-V-domain sequences such as constant regions, linkers, or antigens.
    """
    exploded = measurements.explode("seq_ids").rename({"seq_ids": "seq_id"})
    return exploded.join(load(), on=["patent", "seq_id"], how="inner")
