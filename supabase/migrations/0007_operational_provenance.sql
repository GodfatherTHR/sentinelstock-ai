-- Provenance for rows that are not externally sourced.
--
-- PRODUCT.md requires synthetic data to be labelled as demo data, and the connectors
-- write nothing into sales/shipments, so this column is how seeded history and seeded
-- shipments stay distinguishable from anything a real integration later writes.
alter table sales add column if not exists source text;
alter table shipments add column if not exists source text;

create index if not exists sales_source_idx on sales (source, timestamp desc);
create index if not exists shipments_source_idx on shipments (source);
