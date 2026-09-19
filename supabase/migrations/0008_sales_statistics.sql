-- Daily demand statistics for forecasting.
--
-- PostgREST has no GROUP BY, and aggregating demand in the API would pull every sales row,
-- so the statistics live in one queryable function. It is deliberately NOT security definer:
-- it runs as the caller, so row level security still scopes the rows to the operator's org.
create or replace function public.sales_daily_average(p_days integer default 28)
returns table (
    warehouse_id uuid,
    product_id uuid,
    avg_quantity numeric,
    stddev_quantity numeric,
    sample_days integer
)
language sql
stable
as $$
    select
        s.warehouse_id,
        s.product_id,
        round(avg(s.quantity), 3) as avg_quantity,
        round(coalesce(stddev_samp(s.quantity), 0), 3) as stddev_quantity,
        count(distinct date_trunc('day', s.timestamp))::integer as sample_days
    from public.sales s
    where s.timestamp >= now() - make_interval(days => greatest(p_days, 1))
    group by s.warehouse_id, s.product_id;
$$;

grant execute on function public.sales_daily_average(integer) to authenticated, service_role;
