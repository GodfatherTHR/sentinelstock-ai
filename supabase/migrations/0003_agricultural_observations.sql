-- Phase 2 connector ingestion.
-- Adds: external_source_catalog (cursor tracking) and agricultural_observations (FAOSTAT-shaped rows).
-- Run via Supabase SQL editor AFTER database.sql. This file is self-sufficient: it
-- recreates the RLS helper functions used by its policies so that order vs
-- 0002_phase1_hardening.sql does not matter.
-- The FAOSTAT adapter writes through the API service role; the browser never sees the table directly.

create extension if not exists "uuid-ossp";

do $$
begin
    create type external_provider as enum (
        'faostat',
        'open_food_facts',
        'usda_fooddata',
        'ship_tracking',
        'sentinel2',
        'consumer_signal'
    );
exception
    when duplicate_object then null;
end $$;

-- ============================================================
-- RLS helpers (re-declared idempotently so this migration is order-independent)
-- ============================================================

create or replace function public.get_my_role()
returns user_role
language sql
stable
security definer
set search_path = public
as $$
  select role from public.profiles where id = auth.uid();
$$;

create or replace function public.is_org_member(p_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(p.organization_id = p_organization_id, false)
  from public.profiles p
  where p.id = auth.uid();
$$;

create or replace function public.get_my_organization_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select organization_id from public.profiles where id = auth.uid();
$$;

create table if not exists external_source_catalog (
    provider external_provider primary key,
    dataset_code text not null,
    description text,
    last_cursor text,
    last_pulled_at timestamptz,
    last_status text,
    last_row_count integer default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create or replace function update_external_source_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists external_source_catalog_updated_at on external_source_catalog;
create trigger external_source_catalog_updated_at
before update on external_source_catalog
for each row execute function update_external_source_updated_at();

create table if not exists agricultural_observations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    provider external_provider not null,
    dataset_code text not null,
    region_code text not null,
    region_label text,
    item_code text not null,
    item_label text,
    element_code text not null,
    element_label text,
    year smallint not null,
    value numeric(18,4) not null,
    unit text,
    flag text,
    source_payload jsonb,
    observed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (provider, dataset_code, region_code, item_code, element_code, year)
);

create index if not exists agricultural_obs_lookup_idx
    on agricultural_observations(item_code, region_code, year desc);
create index if not exists agricultural_obs_org_idx
    on agricultural_observations(organization_id, observed_at desc);

alter table external_source_catalog enable row level security;
alter table agricultural_observations enable row level security;

-- Read policies mirror the rest of the schema: org members read; admin roles write.
drop policy if exists "organization catalog read" on external_source_catalog;
create policy "organization catalog read" on external_source_catalog
    for select using (true);

drop policy if exists "organization agricultural read" on agricultural_observations;
create policy "organization agricultural read" on agricultural_observations
    for select using (public.is_org_member(organization_id));

drop policy if exists "authorized agricultural inserts" on agricultural_observations;
create policy "authorized agricultural inserts" on agricultural_observations
    for insert with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'analyst', 'procurement_manager'));

drop policy if exists "authorized agricultural updates" on agricultural_observations;
create policy "authorized agricultural updates" on agricultural_observations
    for update using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'analyst', 'procurement_manager'))
    with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'analyst', 'procurement_manager'));

-- Seed one catalog row so the adapter has something to update.
insert into external_source_catalog (provider, dataset_code, description)
values ('faostat', 'QCL', 'FAOSTAT Crops and Livestock: area harvested, yield, production')
on conflict (provider) do update set description = excluded.description, dataset_code = excluded.dataset_code;
