# Data connectors

Pull-based ingestion workers that load external reference datasets into Supabase. They are
the only components that write external data; the browser and the API never talk to upstream
providers directly.

Schema lives in `supabase/migrations/0004_external_intelligence.sql`.

## Sources

| Source | Upstream | Target tables | What a full run loads |
|---|---|---|---|
| `faostat` (`FBS`) | `bulks-faostat.fao.org` normalized archive | `agricultural_observations` | Food balance sheets: production, trade, supply, feed, losses for 14 areas, 2021+ (~30k rows) |
| `faostat` (`QCL`) | same host | `agricultural_observations` | Crops & livestock production, area harvested, yield (~23k rows) |
| `openfoodfacts` | `world.openfoodfacts.org/api/v2/search` | `food_products` | Products per category with ingredients, allergens, Nutri-Score, NOVA (~2.4k per pass) |
| `usda` | `fdc.nal.usda.gov` bulk CSV | `food_products`, `food_nutrients` | Foundation + SR Legacy foods and a curated 21-nutrient panel (85.8k foods) |
| `maritime` | `meri.digitraffic.fi` (CC BY 4.0, no auth) | `vessels`, `vessel_positions` | AIS snapshot: vessel particulars + live positions (~875 + ~1k per run) |
| `sentinel2` | AWS Earth Search STAC + `sentinel-cogs` | `satellite_scenes`, `crop_index_observations`, `crop_observations` | L2A scenes over 8 agricultural AOIs and NDVI statistics per AOI |
| `enrich` | OpenRouter chat completions | `product_enrichment` | Shelf classification for ingested products, cached per prompt version |

`all` runs every data source (not `enrich`). Use `enrich` explicitly.

## Usage

```powershell
cd services/connectors
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY = '<service-role-or-secret-key>'
$env:OPENROUTER_API_KEY = '<key>'          # only for the enrich step

.\.venv\Scripts\python.exe -m app.worker maritime
.\.venv\Scripts\python.exe -m app.worker faostat --limit 5000
.\.venv\Scripts\python.exe -m app.worker usda --dry-run
.\.venv\Scripts\python.exe -m app.worker all
.\.venv\Scripts\python.exe -m app.worker maritime --loop
```

Writes go through PostgREST with the service-role key, so no database password is needed.
When `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are unset the worker falls back to a direct
`psycopg` connection via `SUPABASE_DB_URL` (useful for local Supabase).

## How a run works

- Every provider yields `(table, rows, on_conflict)` batches; the worker upserts them in order.
- Cursors live in `external_source_catalog`, keyed by `(provider, dataset_code)`. `--limit`
  stops a run early and the next run resumes from the stored cursor.
- Each run appends to `ingestion_runs` (status, cursor before/after, rows per table, error).
- Rows are attributed to `INGEST_ORGANIZATION_ID` so org-scoped tables stay readable via RLS.
- `--dry-run` fetches and counts without writing.
- Reference datasets are world-readable (`select using (true)`); only the service role writes.

## Configuration

| Variable | Used by | Default |
|---|---|---|
| `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` | all | — |
| `SUPABASE_SERVICE_ROLE_KEY` | all | — |
| `SUPABASE_DB_URL` | Postgres fallback sink | — |
| `INGEST_ORGANIZATION_ID` | all | demo org from `supabase/seed.sql` |
| `CONNECTOR_CACHE_DIR` | faostat, usda | `%TEMP%/sentinelstock-connectors` |
| `CONNECTOR_SOURCES` | container entrypoint | `maritime` |
| `CONNECTOR_POLL_SECONDS` | `--loop` | `3600` |
| `FAOSTAT_DATASET` | faostat | `FBS` |
| `FAOSTAT_YEAR_FROM` | faostat | `2021` |
| `FAOSTAT_MAX_ROWS` | faostat | `150000` |
| `FAOSTAT_AREA_FILTERS`, `FAOSTAT_ELEMENT_LABELS` | faostat | curated defaults in `app/faostat.py` |
| `FAOSTAT_REFRESH` | faostat | off (archive cached) |
| `OFF_CATEGORIES`, `OFF_PAGES_PER_CATEGORY`, `OFF_DELAY_SECONDS` | openfoodfacts | 12 categories, 3 pages, 6 s |
| `USDA_DATASETS`, `USDA_NUTRIENT_CODES`, `USDA_MAX_PRODUCTS` | usda | foundation+sr_legacy, 21 codes, 20000 |
| `AIS_MAX_VESSELS` | maritime | `5000` |
| `SENTINEL_AOIS`, `SENTINEL_LOOKBACK_DAYS`, `SENTINEL_CLOUD_MAX`, `SENTINEL_NDVI_SCENES_PER_AOI`, `SENTINEL_COMPUTE_NDVI` | sentinel2 | 8 AOIs, 90 days, cloud < 25%, 2 scenes, on |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | enrich | —, `deepseek/deepseek-v4-flash-0731:free` |
| `ENRICHMENT_MAX_PRODUCTS`, `ENRICHMENT_BATCH_SIZE`, `ENRICHMENT_SOURCE` | enrich | 200, 20, any source |

## Upstream behaviour worth knowing

- **FAOSTAT**'s REST API (`fenixservices`) frequently returns HTTP 521, so the connector reads
  the official bulk archives and filters to the areas, elements, and years the platform uses.
  Archives are cached; `FAOSTAT_REFRESH=1` re-downloads.
- **Open Food Facts** throttles its search endpoint hard (HTTP 503 "Page temporarily
  unavailable"). The connector paces requests, retries with backoff, and skips a throttled
  page instead of failing the run. The published full dump (~10 GB) is intentionally not used.
- **USDA** archives are release-based: bump `ARCHIVE_URLS` in `app/usda_fdc.py` for a newer
  release. `USDA_MAX_PRODUCTS` caps a run; the cursor resumes on the next pass.
- **Sentinel-2** NDVI needs `numpy` + `rasterio` (already in `requirements.txt`). Without them
  the connector still records scene metadata. Bands are read windowed from cloud-optimized
  GeoTIFFs, so only a few KB transfer per AOI. The AOI bbox is reprojected into the tile's UTM
  zone before the window is computed.
- **OpenRouter** free tier allows 50 requests/day. Products are batched per request and results
  cached on `(source, source_id, prompt_version)`, so re-runs only classify new products.

## Tests

```powershell
py -3 -m pytest -q
```
