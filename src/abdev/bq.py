"""BigQuery access with a cost gate.

patents.publications is unpartitioned. A WHERE clause does not reduce bytes
scanned: referencing description_localized scans the full column regardless
of row count. Queries here execute only if run=True, and only under budget_tib.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import google.auth
import polars as pl
from google.cloud import bigquery

from . import manifest

TIB = 1024**4
USD_PER_TIB = 5.0
SRC = "`patents-public-data.patents.publications`"


ADC = Path.home() / ".config/gcloud/application_default_credentials.json"


def project() -> str:
    """Return the GCP project to bill.

    ADC (Application Default Credentials) is a refresh token stored on disk;
    it persists across restarts. quota_project_id is read in preference to
    google.auth's default, which reads gcloud's core/project setting -- a
    separate value that can go stale independently.
    """
    if env := os.environ.get("ABDEV_GCP_PROJECT"):
        return env
    if ADC.exists() and (p := json.loads(ADC.read_text()).get("quota_project_id")):
        return p
    _, p = google.auth.default()
    if not p:
        raise RuntimeError(
            "no project found -- run:\n"
            "  gcloud auth application-default login\n"
            "  gcloud auth application-default set-quota-project YOUR_PROJECT_ID"
        )
    return p


def _client() -> bigquery.Client:
    return bigquery.Client(project=project())


def strings(name: str, values: list[str]) -> list:
    return [bigquery.ArrayQueryParameter(name, "STRING", values)]


def cost(sql: str, params: list | None = None) -> float:
    """Return TiB the query would scan, via dry run. Dry runs are not billed."""
    cfg = bigquery.QueryJobConfig(dry_run=True, query_parameters=params or [])
    return _client().query(sql, job_config=cfg).total_bytes_processed / TIB


def fetch_stream(
    sql: str,
    params: list | None = None,
    out: Path | None = None,
    budget_tib: float = 0.05,
    overwrite: bool = False,
) -> Path | None:
    """Same cost gate as fetch, but stream results to Parquet page by page.

    Used when the result is too large to hold in memory: full-text HTML for
    tens of thousands of patents is ~14 GB, which materialising as a single
    Arrow table would not survive.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    if out is not None and out.exists() and not overwrite:
        print(f"{out} exists, overwrite=False: not executed")
        return out

    tib = cost(sql, params)
    print(f"scan {tib:.4f} TiB, ${max(0.0, tib - 1) * USD_PER_TIB:.2f} after the free 1 TiB/month")
    if tib > budget_tib:
        raise RuntimeError(f"{tib:.3f} TiB exceeds budget {budget_tib} TiB")

    cfg = bigquery.QueryJobConfig(
        query_parameters=params or [],
        maximum_bytes_billed=int(budget_tib * TIB),
    )
    job = _client().query(sql, job_config=cfg)
    manifest.clear(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # The REST API caps a response page at 20 MB and a single patent's HTML can
    # exceed that. The Storage API streams instead, with no per-row limit.
    from google.cloud import bigquery_storage

    bqs = bigquery_storage.BigQueryReadClient()
    writer, rows = None, 0
    for batch in job.result().to_arrow_iterable(bqstorage_client=bqs):
        tbl = pa.Table.from_batches([batch])
        if writer is None:
            writer = pq.ParquetWriter(out, tbl.schema, compression="zstd")
        writer.write_table(tbl)
        rows += tbl.num_rows
        print(f"\r{rows:,} rows", end="", flush=True)
    if writer:
        writer.close()
    manifest.write(
        out, source=SRC.strip("`"), project=project(), job_id=job.job_id,
        bytes_processed=job.total_bytes_processed, bytes_billed=job.total_bytes_billed,
        rows=rows, columns=[], sql=sql.strip(),
    )
    print(f"\n{rows:,} rows -> {out}")
    return out
