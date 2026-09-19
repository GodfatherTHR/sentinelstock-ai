-- Phase 3 external intelligence.
-- Reference datasets ingested by services/connectors:
--   food_products / food_nutrients      Open Food Facts, USDA FoodData Central
--   vessels / vessel_positions          AIS vessel tracking
--   satellite_scenes / crop_index_observations   Sentinel-2 derived crop health
--   product_enrichment                  OpenRouter-backed product classification (cached)
--   ingestion_runs                      run history for every connector
--
-- These are public reference datasets, not tenant business data: reads are open to
-- any authenticated client and writes are service-role only (RLS write policies are
-- intentionally absent). organization_id is carried for provenance so rows can be
-- scoped per tenant later without another migration.

create extension if not exists "uuid-ossp";

-- ============================================================
-- FOOD CATALOG (Open Food Facts + USDA FoodData Central)
-- ============================================================

create table if not exists food_products (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null,
    source_id text not null,
    name text not null,
    brand text,
    category text,
    categories text[],
    barcode text,
    ingredients_text text,
    allergens text[],
    quantity text,
    serving_size text,
    nutriscore_grade text,
    nova_group smallint,
    data_type text,
    image_url text,
    source_payload jsonb,
    observed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (source, source_id)
);

create index if not exists food_products_category_idx on food_products (category);
create index if not exists food_products_barcode_idx on food_products (barcode) where barcode is not null;
create index if not exists food_products_source_idx on food_products (source, observed_at desc);

create table if not exists food_nutrients (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null,
    source_id text not null,
    nutrient_code text not null,
    nutrient_name text,
    nutrient_unit text,
    amount numeric(18,6),
    source_payload jsonb,
    created_at timestamptz not null default now(),
    unique (source, source_id, nutrient_code)
);

create index if not exists food_nutrients_lookup_idx on food_nutrients (source_id);
create index if not exists food_nutrients_code_idx on food_nutrients (nutrient_code);

-- ============================================================
-- MARITIME TRACKING (AIS)
-- ============================================================

create table if not exists vessels (
    mmsi integer primary key,
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null default 'ship_tracking',
    name text,
    call_sign text,
    imo integer,
    ship_type integer,
    ship_type_label text,
    destination text,
    draught numeric(6,2),
    eta timestamptz,
    last_seen_at timestamptz,
    raw jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists vessels_destination_idx on vessels (destination) where destination is not null;
create index if not exists vessels_ship_type_idx on vessels (ship_type);

drop trigger if exists vessels_updated_at on vessels;
create trigger vessels_updated_at
before update on vessels
for each row execute function update_external_source_updated_at();

create table if not exists vessel_positions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null default 'ship_tracking',
    mmsi integer not null,
    observed_at timestamptz not null,
    latitude double precision not null,
    longitude double precision not null,
    speed_knots numeric(8,2),
    course_degrees numeric(6,2),
    heading_degrees numeric(6,2),
    nav_status smallint,
    nav_status_label text,
    raw jsonb,
    created_at timestamptz not null default now(),
    unique (source, mmsi, observed_at)
);

create index if not exists vessel_positions_time_idx on vessel_positions (observed_at desc);
create index if not exists vessel_positions_mmsi_idx on vessel_positions (mmsi, observed_at desc);

-- ============================================================
-- SATELLITE CROP HEALTH (Sentinel-2)
-- ============================================================

create table if not exists satellite_scenes (
    id text primary key,
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null default 'sentinel2',
    collection text,
    platform text,
    aoi_name text,
    crop text,
    acquired_at timestamptz,
    cloud_cover numeric(6,3),
    mgrs_tile text,
    epsg integer,
    bbox double precision[],
    geometry jsonb,
    vegetation_percentage numeric(6,3),
    thumbnail_url text,
    assets jsonb,
    created_at timestamptz not null default now()
);

create index if not exists satellite_scenes_aoi_idx on satellite_scenes (aoi_name, acquired_at desc);
create index if not exists satellite_scenes_time_idx on satellite_scenes (acquired_at desc);

create table if not exists crop_index_observations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null default 'sentinel2',
    scene_id text not null references satellite_scenes(id) on delete cascade,
    aoi_name text not null,
    crop text,
    observed_at timestamptz not null,
    observation_date date not null,
    ndvi_mean numeric(8,5),
    ndvi_p10 numeric(8,5),
    ndvi_p90 numeric(8,5),
    ndvi_std numeric(8,5),
    red_mean numeric(10,5),
    nir_mean numeric(10,5),
    valid_pixel_percentage numeric(6,3),
    cloud_pixel_percentage numeric(6,3),
    health_score numeric(8,5),
    created_at timestamptz not null default now(),
    unique (scene_id, aoi_name)
);

create index if not exists crop_index_aoi_idx on crop_index_observations (aoi_name, observation_date desc);

-- crop_observations is the application-facing table; give it an idempotency key so
-- repeated satellite runs update the same day instead of duplicating it. The index is
-- deliberately not partial: PostgREST/ON CONFLICT cannot target a partial index, and
-- Postgres already treats NULLs as distinct, so unlabelled rows never collide.
drop index if exists crop_observations_source_unique;
create unique index crop_observations_source_unique
    on crop_observations (region, crop, observation_date, satellite_source);

-- ============================================================
-- AI ENRICHMENT (OpenRouter)
-- ============================================================

create table if not exists product_enrichment (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete set null,
    source external_provider not null,
    source_id text not null,
    shelf_category text,
    department text,
    perishability_class text,
    storage_requirements text,
    estimated_shelf_life_days integer,
    model text not null,
    prompt_version text not null,
    payload jsonb,
    created_at timestamptz not null default now(),
    unique (source, source_id, prompt_version)
);

create index if not exists product_enrichment_category_idx on product_enrichment (shelf_category);

-- ============================================================
-- INGESTION RUN HISTORY
-- ============================================================

create table if not exists ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    provider external_provider not null,
    dataset_code text not null,
    status text not null,
    cursor_before text,
    cursor_after text,
    rows_written integer not null default 0,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_message text,
    metadata jsonb
);

create index if not exists ingestion_runs_provider_idx on ingestion_runs (provider, started_at desc);

-- ============================================================
-- ACCESS: public read for reference data, service-role writes, plus catalog seeds
-- ============================================================

do $$
declare
    t text;
begin
    foreach t in array array[
        'food_products',
        'food_nutrients',
        'vessels',
        'vessel_positions',
        'satellite_scenes',
        'crop_index_observations',
        'product_enrichment',
        'ingestion_runs'
    ]
    loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists %I on %I', 'public read ' || t, t);
        execute format('create policy %I on %I for select using (true)', 'public read ' || t, t);
        execute format('grant select on table %I to anon, authenticated', t);
        execute format('grant all on table %I to service_role', t);
    end loop;
end $$;

-- Multi-dataset sources (FAOSTAT FBS + QCL, USDA foundation + sr_legacy) need one
-- cursor row per dataset, so the catalog key becomes (provider, dataset_code).
alter table external_source_catalog drop constraint if exists external_source_catalog_pkey;
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'external_source_catalog_pkey'
          and conrelid = 'external_source_catalog'::regclass
    ) then
        alter table external_source_catalog
            add constraint external_source_catalog_pkey primary key (provider, dataset_code);
    end if;
end $$;

insert into external_source_catalog (provider, dataset_code, description) values
    ('faostat', 'FBS', 'FAOSTAT Food Balance Sheets: supply, trade, feed, losses per country/commodity/year'),
    ('open_food_facts', 'search-api', 'Open Food Facts catalog: ingredients, allergens, Nutri-Score, NOVA'),
    ('usda_fooddata', 'foundation+sr_legacy', 'USDA FoodData Central foundation and SR Legacy nutrient panels'),
    ('ship_tracking', 'digitraffic-ais', 'Digitraffic AIS vessel metadata and live positions'),
    ('sentinel2', 'sentinel-2-l2a', 'Sentinel-2 L2A scene metadata and NDVI crop-health indices')
on conflict (provider, dataset_code) do update set
    dataset_code = excluded.dataset_code,
    description = excluded.description,
    updated_at = now();
