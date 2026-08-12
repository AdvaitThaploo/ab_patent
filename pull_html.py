"""Pull description HTML for every EBI-covered antibody patent.

One query for all 46k patents: patents.publications is unpartitioned, so the
scan is billed per column regardless of row count. Pulling 200 patents and
pulling 46,453 cost the same.
"""

import sys
sys.path.insert(0, "src")
from abdev import bq, ebi, paths

SQL = """
SELECT
  publication_number,
  REGEXP_EXTRACT(publication_number, r'^([A-Z]{2}-[0-9]+)') AS patent,
  publication_date,
  (SELECT text FROM UNNEST(description_localized_html) WHERE language='en' LIMIT 1) AS html
FROM `patents-public-data.patents.publications`
WHERE REGEXP_EXTRACT(publication_number, r'^([A-Z]{2}-[0-9]+)') IN UNNEST(@patents)
  AND country_code = 'US'
  AND EXISTS(SELECT 1 FROM UNNEST(cpc) c WHERE c.code LIKE 'C07K16/%')
  AND (SELECT text FROM UNNEST(description_localized_html) WHERE language='en' LIMIT 1) IS NOT NULL
"""

pats = ebi.patents().to_list()
print(f"{len(pats):,} EBI patents")
bq.fetch_stream(SQL, bq.strings("patents", pats), out=paths.HTML, budget_tib=1.5)
