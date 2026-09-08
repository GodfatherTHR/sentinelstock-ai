-- ============================================================
-- SENTINELSTOCK AI
-- SUPABASE / POSTGRESQL DATABASE
-- ============================================================

create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";
create extension if not exists "vector";

-- ============================================================
-- ENUMS
-- ============================================================

do $$
begin

    create type user_role as enum (
        'admin',
        'warehouse_manager',
        'procurement_manager',
        'analyst',
        'viewer'
    );

exception
    when duplicate_object then null;
end $$;


do $$
begin

    create type purchase_order_status as enum (
        'draft',
        'pending_approval',
        'approved',
        'ordered',
        'partially_received',
        'received',
        'cancelled',
        'rejected'
    );

exception
    when duplicate_object then null;
end $$;


do $$
begin

    create type decision_type as enum (
        'RESTOCK',
        'TRANSFER',
        'NO_ACTION',
        'EXPEDITE',
        'REDUCE_ORDER',
        'CANCEL_ORDER'
    );

exception
    when duplicate_object then null;
end $$;


do $$
begin

    create type risk_level as enum (
        'LOW',
        'MEDIUM',
        'HIGH',
        'CRITICAL'
    );

exception
    when duplicate_object then null;
end $$;


-- ============================================================
-- ORGANIZATIONS
-- Multi-tenant ready
-- ============================================================

create table if not exists organizations (
    id uuid primary key default gen_random_uuid(),

    name text not null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


-- ============================================================
-- USER PROFILES
-- ============================================================

create table if not exists profiles (
    id uuid primary key references auth.users(id) on delete cascade,

    organization_id uuid references organizations(id) on delete cascade,

    full_name text,

    role user_role not null default 'viewer',

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


-- ============================================================
-- WAREHOUSES
-- ============================================================

create table if not exists warehouses (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    name text not null,

    region text not null,

    latitude double precision,

    longitude double precision,

    capacity numeric(14,2) not null default 0,

    temperature_zone text,

    active boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint warehouse_capacity_nonnegative
        check (capacity >= 0)
);


-- ============================================================
-- PRODUCTS
-- ============================================================

create table if not exists products (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    sku text not null,

    barcode text,

    name text not null,

    category text,

    brand text,

    unit text not null default 'unit',

    shelf_life_days integer,

    is_perishable boolean not null default false,

    temperature_zone text,

    active boolean not null default true,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint shelf_life_positive
        check (
            shelf_life_days is null
            or shelf_life_days > 0
        )
);


-- ============================================================
-- UNIQUE PRODUCT SKU PER ORGANIZATION
-- ============================================================

create unique index if not exists products_org_sku_unique
on products(organization_id, sku);


-- ============================================================
-- INVENTORY
-- ============================================================

create table if not exists inventory (
    id uuid primary key default gen_random_uuid(),

    warehouse_id uuid not null
        references warehouses(id) on delete cascade,

    product_id uuid not null
        references products(id) on delete cascade,

    quantity numeric(14,3) not null default 0,

    reserved numeric(14,3) not null default 0,

    incoming numeric(14,3) not null default 0,

    reorder_point numeric(14,3) not null default 0,

    safety_stock numeric(14,3) not null default 0,

    average_daily_demand numeric(14,3) not null default 0,

    days_of_inventory numeric(14,3),

    stockout_probability numeric(8,5),

    updated_at timestamptz not null default now(),

    unique(warehouse_id, product_id),

    constraint inventory_quantity_nonnegative
        check (quantity >= 0),

    constraint inventory_reserved_nonnegative
        check (reserved >= 0),

    constraint inventory_incoming_nonnegative
        check (incoming >= 0),

    constraint inventory_reserved_valid
        check (reserved <= quantity)
);


-- ============================================================
-- INVENTORY MOVEMENTS
-- Important for audit/history
-- ============================================================

create table if not exists inventory_movements (
    id uuid primary key default gen_random_uuid(),

    warehouse_id uuid not null
        references warehouses(id) on delete cascade,

    product_id uuid not null
        references products(id) on delete cascade,

    movement_type text not null,

    quantity numeric(14,3) not null,

    reference_id uuid,

    notes text,

    created_by uuid references auth.users(id),

    created_at timestamptz not null default now()
);


-- ============================================================
-- SALES
-- ============================================================

create table if not exists sales (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    warehouse_id uuid not null
        references warehouses(id) on delete cascade,

    product_id uuid not null
        references products(id) on delete cascade,

    quantity numeric(14,3) not null,

    price numeric(14,2) not null,

    timestamp timestamptz not null default now(),

    created_at timestamptz not null default now(),

    constraint sale_quantity_positive
        check (quantity > 0),

    constraint sale_price_nonnegative
        check (price >= 0)
);


-- ============================================================
-- SUPPLIERS
-- ============================================================

create table if not exists suppliers (
    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    name text not null,

    region text,

    lead_time_days integer not null default 0,

    minimum_order_quantity numeric(14,3) not null default 0,

    active boolean not null default true,

    created_at timestamptz not null default now(),

    constraint supplier_lead_time_valid
        check (lead_time_days >= 0),

    constraint supplier_moq_valid
        check (minimum_order_quantity >= 0)
);


-- ============================================================
-- SUPPLIER PRODUCTS
-- Supplier-specific pricing and constraints
-- ============================================================

create table if not exists supplier_products (

    id uuid primary key default gen_random_uuid(),

    supplier_id uuid not null
        references suppliers(id) on delete cascade,

    product_id uuid not null
        references products(id) on delete cascade,

    unit_price numeric(14,2) not null default 0,

    minimum_order_quantity numeric(14,3),

    lead_time_days integer,

    maximum_capacity numeric(14,3),

    active boolean not null default true,

    created_at timestamptz not null default now(),

    unique(supplier_id, product_id),

    constraint supplier_product_price_valid
        check (unit_price >= 0)
);


-- ============================================================
-- PURCHASE ORDERS
-- ============================================================

create table if not exists purchase_orders (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    supplier_id uuid not null
        references suppliers(id),

    warehouse_id uuid not null
        references warehouses(id),

    status purchase_order_status not null default 'draft',

    expected_delivery_date timestamptz,

    total_amount numeric(16,2) not null default 0,

    ai_generated boolean not null default false,

    ai_decision_id uuid,

    created_by uuid references auth.users(id),

    approved_by uuid references auth.users(id),

    approved_at timestamptz,

    created_at timestamptz not null default now(),

    updated_at timestamptz not null default now()
);


-- ============================================================
-- PURCHASE ORDER ITEMS
-- ============================================================

create table if not exists purchase_order_items (

    id uuid primary key default gen_random_uuid(),

    order_id uuid not null
        references purchase_orders(id) on delete cascade,

    product_id uuid not null
        references products(id),

    quantity numeric(14,3) not null,

    unit_price numeric(14,2) not null,

    received_quantity numeric(14,3) not null default 0,

    created_at timestamptz not null default now(),

    constraint po_item_quantity_positive
        check (quantity > 0),

    constraint po_item_price_nonnegative
        check (unit_price >= 0)
);


-- ============================================================
-- SENTIMENT
-- ============================================================

create table if not exists sentiment (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    region text not null,

    product_id uuid
        references products(id) on delete cascade,

    sentiment_score numeric(8,5),

    demand_signal numeric(8,5),

    confidence numeric(8,5),

    sentiment_change numeric(8,5),

    sample_count integer default 0,

    source text,

    timestamp timestamptz not null default now(),

    created_at timestamptz not null default now()
);


-- ============================================================
-- FORECASTS
-- ============================================================

create table if not exists forecasts (

    id uuid primary key default gen_random_uuid(),

    warehouse_id uuid not null
        references warehouses(id) on delete cascade,

    product_id uuid not null
        references products(id) on delete cascade,

    forecast_date date not null,

    predicted_demand numeric(14,3) not null,

    lower_bound numeric(14,3),

    upper_bound numeric(14,3),

    confidence numeric(8,5),

    model_name text,

    model_version text,

    created_at timestamptz not null default now(),

    unique(
        warehouse_id,
        product_id,
        forecast_date
    )
);


-- ============================================================
-- SHIPMENTS
-- ============================================================

create table if not exists shipments (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    supplier_id uuid references suppliers(id),

    destination uuid references warehouses(id),

    vessel_id text,

    origin text,

    eta timestamptz,

    status text,

    latitude double precision,

    longitude double precision,

    risk_score numeric(8,5),

    delay_days numeric(8,2),

    last_updated timestamptz,

    created_at timestamptz not null default now()
);


-- ============================================================
-- CROP OBSERVATIONS
-- ============================================================

create table if not exists crop_observations (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    region text not null,

    crop text not null,

    ndvi numeric(8,5),

    health_score numeric(8,5),

    estimated_output numeric(16,3),

    cloud_coverage numeric(8,5),

    satellite_source text,

    observation_date date,

    timestamp timestamptz not null default now(),

    created_at timestamptz not null default now()
);


-- ============================================================
-- RISK SCORES
-- ============================================================

create table if not exists risk_scores (

    id uuid primary key default gen_random_uuid(),

    warehouse_id uuid
        references warehouses(id) on delete cascade,

    product_id uuid
        references products(id) on delete cascade,

    demand_risk numeric(8,5) default 0,

    supply_risk numeric(8,5) default 0,

    logistics_risk numeric(8,5) default 0,

    inventory_risk numeric(8,5) default 0,

    sentiment_volatility numeric(8,5) default 0,

    overall_score numeric(8,5) default 0,

    risk_level risk_level default 'LOW',

    created_at timestamptz not null default now()
);


-- ============================================================
-- WAREHOUSE TRANSFERS
-- ============================================================

create table if not exists warehouse_transfers (

    id uuid primary key default gen_random_uuid(),

    product_id uuid not null
        references products(id),

    source_warehouse_id uuid not null
        references warehouses(id),

    destination_warehouse_id uuid not null
        references warehouses(id),

    quantity numeric(14,3) not null,

    status text not null default 'pending',

    expected_arrival timestamptz,

    created_by uuid references auth.users(id),

    created_at timestamptz not null default now(),

    constraint transfer_positive_quantity
        check (quantity > 0),

    constraint transfer_different_warehouses
        check (
            source_warehouse_id <> destination_warehouse_id
        )
);


-- ============================================================
-- AI AGENT DECISIONS
-- ============================================================

create table if not exists agent_decisions (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    decision_type decision_type not null,

    warehouse_id uuid
        references warehouses(id),

    product_id uuid
        references products(id),

    recommendation jsonb not null,

    reasoning text,

    drivers jsonb,

    confidence numeric(8,5),

    risk_score numeric(8,5),

    requires_human_approval boolean not null default true,

    approval_status text default 'pending',

    approved_by uuid references auth.users(id),

    approved_at timestamptz,

    executed_at timestamptz,

    created_at timestamptz not null default now()
);


-- ============================================================
-- AUDIT LOG
-- ============================================================

create table if not exists audit_logs (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id) on delete cascade,

    user_id uuid references auth.users(id),

    action text not null,

    entity_type text,

    entity_id uuid,

    old_data jsonb,

    new_data jsonb,

    metadata jsonb,

    created_at timestamptz not null default now()
);


-- ============================================================
-- AGENT RUNS
-- ============================================================

create table if not exists agent_runs (

    id uuid primary key default gen_random_uuid(),

    organization_id uuid references organizations(id),

    agent_name text not null,

    status text not null default 'running',

    input jsonb,

    output jsonb,

    error_message text,

    started_at timestamptz not null default now(),

    completed_at timestamptz
);


-- ============================================================
-- INDEXES
-- ============================================================

create index if not exists inventory_warehouse_idx
on inventory(warehouse_id);

create index if not exists inventory_product_idx
on inventory(product_id);

create index if not exists sales_warehouse_product_time_idx
on sales(warehouse_id, product_id, timestamp desc);

create index if not exists forecasts_lookup_idx
on forecasts(warehouse_id, product_id, forecast_date);

create index if not exists sentiment_region_product_time_idx
on sentiment(region, product_id, timestamp desc);

create index if not exists shipments_eta_idx
on shipments(eta);

create index if not exists crop_region_time_idx
on crop_observations(region, timestamp desc);

create index if not exists agent_decisions_pending_idx
on agent_decisions(approval_status, created_at desc);

create index if not exists purchase_orders_status_idx
on purchase_orders(status);

create index if not exists audit_logs_entity_idx
on audit_logs(entity_type, entity_id);


-- ============================================================
-- UPDATED_AT FUNCTION
-- ============================================================

create or replace function update_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;


-- ============================================================
-- UPDATED_AT TRIGGERS
-- ============================================================

drop trigger if exists warehouses_updated_at on warehouses;

create trigger warehouses_updated_at
before update on warehouses
for each row
execute function update_updated_at();


drop trigger if exists products_updated_at on products;

create trigger products_updated_at
before update on products
for each row
execute function update_updated_at();


drop trigger if exists inventory_updated_at on inventory;

create trigger inventory_updated_at
before update on inventory
for each row
execute function update_updated_at();


drop trigger if exists purchase_orders_updated_at on purchase_orders;

create trigger purchase_orders_updated_at
before update on purchase_orders
for each row
execute function update_updated_at();


drop trigger if exists profiles_updated_at on profiles;

create trigger profiles_updated_at
before update on profiles
for each row
execute function update_updated_at();


-- ============================================================
-- INVENTORY DERIVED METRICS
-- ============================================================

create or replace function calculate_inventory_metrics()
returns trigger
language plpgsql
as $$
begin

    if new.average_daily_demand > 0 then

        new.days_of_inventory =
            greatest(
                (
                    new.quantity
                    - new.reserved
                    + new.incoming
                ) / new.average_daily_demand,
                0
            );

    else

        new.days_of_inventory = null;

    end if;

    return new;

end;
$$;


drop trigger if exists inventory_metrics_trigger
on inventory;

create trigger inventory_metrics_trigger

before insert or update
on inventory

for each row

execute function calculate_inventory_metrics();


-- ============================================================
-- SALE → INVENTORY DECREMENT
-- ============================================================

create or replace function process_sale_inventory()
returns trigger
language plpgsql
as $$
begin

    update inventory

    set quantity = quantity - new.quantity,

        updated_at = now()

    where warehouse_id = new.warehouse_id

      and product_id = new.product_id

      and quantity >= new.quantity;

    if not found then

        raise exception
        'Insufficient inventory for product % in warehouse %',
        new.product_id,
        new.warehouse_id;

    end if;

    insert into inventory_movements(
        warehouse_id,
        product_id,
        movement_type,
        quantity,
        reference_id
    )

    values(
        new.warehouse_id,
        new.product_id,
        'SALE',
        -new.quantity,
        new.id
    );

    return new;

end;
$$;


drop trigger if exists sale_inventory_trigger
on sales;

create trigger sale_inventory_trigger

after insert
on sales

for each row

execute function process_sale_inventory();


-- ============================================================
-- PURCHASE ORDER → INCOMING INVENTORY
-- ============================================================

create or replace function update_incoming_inventory()
returns trigger
language plpgsql
as $$
declare
    total_qty numeric;
begin

    select coalesce(sum(quantity - received_quantity), 0)
    into total_qty

    from purchase_order_items

    where order_id = new.order_id;

    update inventory

    set incoming = incoming + greatest(
        total_qty - coalesce(
            (
                select sum(quantity - received_quantity)
                from purchase_order_items
                where order_id = old.order_id
            ),
            0
        ),
        0
    )

    where warehouse_id = (
        select warehouse_id
        from purchase_orders
        where id = new.order_id
    )

    and product_id = new.product_id;

    return new;

end;
$$;


-- ============================================================
-- PURCHASE ORDER TOTAL
-- ============================================================

create or replace function calculate_purchase_order_total()
returns trigger
language plpgsql
as $$
begin

    update purchase_orders

    set total_amount = (
        select coalesce(
            sum(quantity * unit_price),
            0
        )
        from purchase_order_items
        where order_id = new.order_id
    )

    where id = new.order_id;

    return new;

end;
$$;


drop trigger if exists purchase_order_total_trigger
on purchase_order_items;

create trigger purchase_order_total_trigger

after insert or update or delete
on purchase_order_items

for each row

execute function calculate_purchase_order_total();


-- ============================================================
-- LOW INVENTORY DETECTION
-- ============================================================

create or replace function get_low_inventory()

returns table (

    warehouse_id uuid,
    product_id uuid,
    available_inventory numeric,
    reorder_point numeric,
    days_of_inventory numeric

)

language sql
stable

as $$

    select

        warehouse_id,

        product_id,

        (
            quantity
            - reserved
            + incoming
        ) as available_inventory,

        reorder_point,

        days_of_inventory

    from inventory

    where (
        quantity
        - reserved
        + incoming
    ) <= reorder_point;

$$;


-- ============================================================
-- STOCKOUT RISK
-- ============================================================

create or replace function calculate_stockout_probability(
    p_inventory numeric,
    p_daily_demand numeric,
    p_lead_time numeric
)

returns numeric

language plpgsql
immutable

as $$

declare
    coverage numeric;
begin

    if p_daily_demand <= 0 then
        return 0;
    end if;

    coverage :=
        p_inventory / p_daily_demand;

    if coverage < p_lead_time then
        return 0.95;
    elsif coverage < p_lead_time + 2 then
        return 0.65;
    elsif coverage < p_lead_time + 5 then
        return 0.30;
    else
        return 0.05;
    end if;

end;
$$;

create or replace view inventory_status as
select
    i.id,
    i.warehouse_id,
    w.name as warehouse_name,
    i.product_id,
    p.sku,
    p.name as product_name,

    i.quantity,
    i.reserved,
    i.incoming,

    (
        i.quantity
        - i.reserved
        + i.incoming
    ) as available_inventory,

    i.reorder_point,
    i.safety_stock,
    i.average_daily_demand,
    i.days_of_inventory,
    i.stockout_probability,

    case

        when (
            i.quantity
            - i.reserved
            + i.incoming
        ) <= 0
        then 'CRITICAL'

        when (
            i.quantity
            - i.reserved
            + i.incoming
        ) <= i.reorder_point
        then 'HIGH'

        when (
            i.quantity
            - i.reserved
            + i.incoming
        ) <= i.reorder_point * 1.25
        then 'MEDIUM'

        else 'LOW'

    end as inventory_status

from inventory i

join warehouses w
    on w.id = i.warehouse_id

join products p
    on p.id = i.product_id;

alter table organizations enable row level security;
alter table profiles enable row level security;
alter table warehouses enable row level security;
alter table products enable row level security;
alter table inventory enable row level security;
alter table inventory_movements enable row level security;
alter table sales enable row level security;
alter table suppliers enable row level security;
alter table supplier_products enable row level security;
alter table purchase_orders enable row level security;
alter table purchase_order_items enable row level security;
alter table sentiment enable row level security;
alter table forecasts enable row level security;
alter table shipments enable row level security;
alter table crop_observations enable row level security;
alter table risk_scores enable row level security;
alter table warehouse_transfers enable row level security;
alter table agent_decisions enable row level security;
alter table audit_logs enable row level security;
alter table agent_runs enable row level security;

create or replace function get_my_organization_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$

    select organization_id
    from profiles
    where id = auth.uid();

$$;

create policy "organization warehouses"
on warehouses

for all

using (
    organization_id = get_my_organization_id()
)

with check (
    organization_id = get_my_organization_id()
);

create policy "organization products"
on products

for all

using (
    organization_id = get_my_organization_id()
)

with check (
    organization_id = get_my_organization_id()
);

create policy "organization inventory"
on inventory

for all

using (
    exists (
        select 1
        from warehouses w
        where w.id = inventory.warehouse_id
        and w.organization_id = get_my_organization_id()
    )
)

with check (
    exists (
        select 1
        from warehouses w
        where w.id = inventory.warehouse_id
        and w.organization_id = get_my_organization_id()
    )
);