-- Write policies for the tables services/api mutates under the caller's JWT.
-- Reads were already org-scoped in 0002; these close the write gaps so that
-- approvals, forecast runs, and purchase orders are role-gated in the database
-- rather than relying on the API process alone.

-- Forecasts: planning roles persist the baseline model output.
drop policy if exists "authorized forecast inserts" on public.forecasts;
create policy "authorized forecast inserts" on public.forecasts for insert
  with check (
    exists (
      select 1 from public.warehouses w
      where w.id = forecasts.warehouse_id
        and public.is_org_member(w.organization_id)
        and public.get_my_role() in ('admin', 'procurement_manager', 'analyst')
    )
  );

drop policy if exists "authorized forecast updates" on public.forecasts;
create policy "authorized forecast updates" on public.forecasts for update
  using (
    exists (
      select 1 from public.warehouses w
      where w.id = forecasts.warehouse_id
        and public.is_org_member(w.organization_id)
        and public.get_my_role() in ('admin', 'procurement_manager', 'analyst')
    )
  )
  with check (
    exists (
      select 1 from public.warehouses w
      where w.id = forecasts.warehouse_id
        and public.is_org_member(w.organization_id)
        and public.get_my_role() in ('admin', 'procurement_manager', 'analyst')
    )
  );

-- Agent decisions: the API appends the immutable decision record on approval.
drop policy if exists "authorized decision inserts" on public.agent_decisions;
create policy "authorized decision inserts" on public.agent_decisions for insert
  with check (
    public.is_org_member(organization_id)
    and public.get_my_role() in ('admin', 'procurement_manager', 'warehouse_manager', 'analyst')
  );

-- Purchase order line items follow the authorization of their parent order.
drop policy if exists "authorized purchase order item inserts" on public.purchase_order_items;
create policy "authorized purchase order item inserts" on public.purchase_order_items for insert
  with check (
    exists (
      select 1 from public.purchase_orders po
      where po.id = purchase_order_items.order_id
        and public.is_org_member(po.organization_id)
        and public.get_my_role() in ('admin', 'procurement_manager')
    )
  );
