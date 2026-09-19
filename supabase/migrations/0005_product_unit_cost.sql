-- Product unit cost, so inventory value and replenishment spend are computed from data
-- instead of hard-coded demo constants.
alter table products add column if not exists unit_cost numeric(14,2) not null default 0;
