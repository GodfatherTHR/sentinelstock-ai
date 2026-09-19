-- Seeded operational history so demand forecasting reads an observed time series and the
-- logistics lane has shipment records. Every row is labelled source = 'synthetic-demo';
-- run this after supabase/seed.sql. Idempotent: synthetic rows are replaced on each run.

-- ============================================================
-- 90 days of sales history for every warehouse × SKU pair
-- Average daily demand matches inventory.average_daily_demand, with deterministic
-- day-to-day variation (±10% from a hash) and a weekend uplift.
-- ============================================================
-- Backfilled history must not consume today's stock: sale_inventory_trigger decrements
-- inventory for live sales, so it is disabled for this insert and re-enabled immediately.
-- The whole file runs in one transaction, so a failure rolls the toggle back too.
alter table public.sales disable trigger sale_inventory_trigger;
delete from public.sales where source = 'synthetic-demo';

with pairs as (
    select i.warehouse_id,
           i.product_id,
           i.average_daily_demand,
           p.unit_cost,
           w.organization_id
    from public.inventory i
    join public.products p on p.id = i.product_id
    join public.warehouses w on w.id = i.warehouse_id
    where i.average_daily_demand > 0
),
days as (
    select generate_series(current_date - interval '89 days', current_date, interval '1 day')::date as day
)
insert into public.sales (organization_id, warehouse_id, product_id, quantity, price, timestamp, source)
select
    pairs.organization_id,
    pairs.warehouse_id,
    pairs.product_id,
    greatest(round((
        pairs.average_daily_demand
        * (1 + (((('x' || substr(md5(pairs.warehouse_id::text || pairs.product_id::text || days.day::text), 1, 8))::bit(32)::bigint % 21) - 10) / 100.0))
        * (case when extract(isodow from days.day) >= 6 then 1.08 else 0.97 end)
    )::numeric, 1), 1),
    pairs.unit_cost,
    days.day::timestamptz + time '12:00',
    'synthetic-demo'
from pairs
cross join days;

alter table public.sales enable trigger sale_inventory_trigger;

-- ============================================================
-- Inbound shipments for the supplier / warehouse network
-- ============================================================
delete from public.shipments where source = 'synthetic-demo';

insert into public.shipments (organization_id, supplier_id, destination, vessel_id, origin, eta, status, latitude, longitude, risk_score, delay_days, last_updated, source)
values
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000002002', '00000000-0000-0000-0000-000000000102',
     'MV Bengal Star', 'Singapore', now() + interval '3 days', 'In transit', 20.12, 89.32, 0.64, 2.0, now(), 'synthetic-demo'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000002001', '00000000-0000-0000-0000-000000000101',
     'Road convoy BD-22', 'Kolkata', now() + interval '1 day', 'Arriving today', 23.45, 90.11, 0.18, 0.0, now(), 'synthetic-demo'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000002003', '00000000-0000-0000-0000-000000000104',
     'MV Sylhet Trader', 'Chattogram', now() + interval '6 days', 'At sea', 22.91, 91.44, 0.35, 0.5, now(), 'synthetic-demo'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000002002', '00000000-0000-0000-0000-000000000103',
     'Road convoy MH-07', 'Chattogram', now() - interval '1 day', 'Delayed at origin port', 23.62, 90.51, 0.81, 3.5, now(), 'synthetic-demo'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000002001', '00000000-0000-0000-0000-000000000102',
     'MV Bay Carrier', 'Singapore', now() + interval '9 days', 'Loading at origin', 18.74, 93.11, 0.22, 0.0, now(), 'synthetic-demo');
