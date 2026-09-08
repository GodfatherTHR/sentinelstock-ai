-- Phase 1 hardening for the existing database.sql schema.
-- Run with Supabase SQL editor or the service role. Do not expose service-role credentials to the browser.

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
  select p.organization_id = p_organization_id
  from public.profiles p
  where p.id = auth.uid();
$$;

-- Replace the three draft policies with explicit, repeatable policies.
drop policy if exists "organization warehouses" on public.warehouses;
create policy "organization warehouses" on public.warehouses for select
  using (public.is_org_member(organization_id));
create policy "warehouse managers write warehouses" on public.warehouses for all
  using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'warehouse_manager'))
  with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'warehouse_manager'));

drop policy if exists "organization products" on public.products;
create policy "organization products" on public.products for select
  using (public.is_org_member(organization_id));
create policy "catalog managers write products" on public.products for all
  using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager'))
  with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager'));

drop policy if exists "organization inventory" on public.inventory;
create policy "organization inventory" on public.inventory for select
  using (exists (select 1 from public.warehouses w where w.id = inventory.warehouse_id and public.is_org_member(w.organization_id)));
create policy "authorized inventory writes" on public.inventory for all
  using (exists (select 1 from public.warehouses w where w.id = inventory.warehouse_id and public.is_org_member(w.organization_id) and public.get_my_role() in ('admin', 'warehouse_manager')))
  with check (exists (select 1 from public.warehouses w where w.id = inventory.warehouse_id and public.is_org_member(w.organization_id) and public.get_my_role() in ('admin', 'warehouse_manager')));

-- Tables with a direct tenant key.
drop policy if exists "organization access organizations" on public.organizations;
create policy "organization access organizations" on public.organizations for select using (id = (select organization_id from public.profiles where id = auth.uid()));
drop policy if exists "organization access profiles" on public.profiles;
create policy "organization access profiles" on public.profiles for select using (id = auth.uid() or public.is_org_member(organization_id));
drop policy if exists "organization sales" on public.sales;
create policy "organization sales" on public.sales for select using (public.is_org_member(organization_id));
create policy "authorized sales" on public.sales for insert with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'warehouse_manager'));
drop policy if exists "organization suppliers" on public.suppliers;
create policy "organization suppliers" on public.suppliers for select using (public.is_org_member(organization_id));
create policy "authorized suppliers" on public.suppliers for all using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager')) with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager'));
drop policy if exists "organization sentiment" on public.sentiment;
create policy "organization sentiment" on public.sentiment for select using (public.is_org_member(organization_id));
drop policy if exists "organization shipments" on public.shipments;
create policy "organization shipments" on public.shipments for select using (public.is_org_member(organization_id));
drop policy if exists "organization crops" on public.crop_observations;
create policy "organization crops" on public.crop_observations for select using (public.is_org_member(organization_id));
drop policy if exists "organization decisions" on public.agent_decisions;
create policy "organization decisions" on public.agent_decisions for select using (public.is_org_member(organization_id));
create policy "authorized decision approvals" on public.agent_decisions for update using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager', 'warehouse_manager')) with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager', 'warehouse_manager'));
drop policy if exists "organization runs" on public.agent_runs;
create policy "organization runs" on public.agent_runs for select using (public.is_org_member(organization_id));
drop policy if exists "organization audit" on public.audit_logs;
create policy "organization audit" on public.audit_logs for select using (public.is_org_member(organization_id));
create policy "append organization audit" on public.audit_logs for insert with check (public.is_org_member(organization_id));

-- Tables scoped through a warehouse/product/order relationship.
drop policy if exists "organization movements" on public.inventory_movements;
create policy "organization movements" on public.inventory_movements for select using (exists (select 1 from public.warehouses w where w.id = inventory_movements.warehouse_id and public.is_org_member(w.organization_id)));
drop policy if exists "organization supplier products" on public.supplier_products;
create policy "organization supplier products" on public.supplier_products for select using (exists (select 1 from public.suppliers s where s.id = supplier_products.supplier_id and public.is_org_member(s.organization_id)));
drop policy if exists "organization purchase orders" on public.purchase_orders;
create policy "organization purchase orders" on public.purchase_orders for select using (public.is_org_member(organization_id));
create policy "authorized purchase order inserts" on public.purchase_orders for insert with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager'));
create policy "authorized purchase order updates" on public.purchase_orders for update using (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager')) with check (public.is_org_member(organization_id) and public.get_my_role() in ('admin', 'procurement_manager'));
drop policy if exists "organization purchase order items" on public.purchase_order_items;
create policy "organization purchase order items" on public.purchase_order_items for select using (exists (select 1 from public.purchase_orders po where po.id = purchase_order_items.order_id and public.is_org_member(po.organization_id)));
drop policy if exists "organization forecasts" on public.forecasts;
create policy "organization forecasts" on public.forecasts for select using (exists (select 1 from public.warehouses w where w.id = forecasts.warehouse_id and public.is_org_member(w.organization_id)));
drop policy if exists "organization risks" on public.risk_scores;
create policy "organization risks" on public.risk_scores for select using (exists (select 1 from public.warehouses w where w.id = risk_scores.warehouse_id and public.is_org_member(w.organization_id)));
drop policy if exists "organization transfers" on public.warehouse_transfers;
create policy "organization transfers" on public.warehouse_transfers for select using (exists (select 1 from public.warehouses w where w.id = warehouse_transfers.destination_warehouse_id and public.is_org_member(w.organization_id)));
create policy "authorized transfer inserts" on public.warehouse_transfers for insert with check (exists (select 1 from public.warehouses w where w.id = warehouse_transfers.destination_warehouse_id and public.is_org_member(w.organization_id) and public.get_my_role() in ('admin', 'warehouse_manager', 'procurement_manager')));
create policy "authorized transfer updates" on public.warehouse_transfers for update using (exists (select 1 from public.warehouses w where w.id = warehouse_transfers.destination_warehouse_id and public.is_org_member(w.organization_id) and public.get_my_role() in ('admin', 'warehouse_manager', 'procurement_manager'))) with check (exists (select 1 from public.warehouses w where w.id = warehouse_transfers.destination_warehouse_id and public.is_org_member(w.organization_id) and public.get_my_role() in ('admin', 'warehouse_manager', 'procurement_manager')));

create index if not exists sales_org_time_idx on public.sales(organization_id, timestamp desc);
create index if not exists purchase_orders_org_status_idx on public.purchase_orders(organization_id, status, created_at desc);
create index if not exists agent_decisions_org_status_idx on public.agent_decisions(organization_id, approval_status, created_at desc);
