-- Synthetic Phase 1 seed. Run with the Supabase service role after database.sql.
-- Values are intentionally realistic-looking but are not production data.

insert into public.organizations (id, name)
values ('00000000-0000-0000-0000-000000000001', 'SentinelStock Demo Network')
on conflict (id) do update set name = excluded.name;

insert into public.warehouses (id, organization_id, name, region, latitude, longitude, capacity, temperature_zone)
values
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', 'Dhaka Central', 'Dhaka', 23.8103, 90.4125, 98000, 'ambient + chilled'),
  ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000001', 'Chattogram Port', 'Chattogram', 22.3569, 91.7832, 72000, 'ambient + chilled'),
  ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000001', 'Rajshahi North', 'Rajshahi', 24.3745, 88.6042, 54000, 'ambient'),
  ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000001', 'Sylhet East', 'Sylhet', 24.8949, 91.8687, 42000, 'ambient + chilled')
on conflict (id) do update set name = excluded.name, capacity = excluded.capacity;

insert into public.products (id, organization_id, sku, name, category, unit, shelf_life_days, is_perishable, temperature_zone)
values
  ('00000000-0000-0000-0000-000000001001', '00000000-0000-0000-0000-000000000001', 'OIL-1L-SUN', 'Sunflower Oil 1L', 'Cooking Oil', 'case', 365, false, 'ambient'),
  ('00000000-0000-0000-0000-000000001002', '00000000-0000-0000-0000-000000000001', 'RICE-5KG-BAS', 'Basmati Rice 5kg', 'Staples', 'bag', 540, false, 'ambient'),
  ('00000000-0000-0000-0000-000000001003', '00000000-0000-0000-0000-000000000001', 'MILK-1L-UHT', 'UHT Milk 1L', 'Dairy', 'case', 180, true, 'chilled'),
  ('00000000-0000-0000-0000-000000001004', '00000000-0000-0000-0000-000000000001', 'DAL-1KG-RED', 'Red Lentils 1kg', 'Staples', 'bag', 360, false, 'ambient')
on conflict (id) do update set name = excluded.name, category = excluded.category;

insert into public.inventory (warehouse_id, product_id, quantity, reserved, incoming, reorder_point, safety_stock, average_daily_demand, stockout_probability)
values
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000001001', 4200, 540, 1800, 8640, 2880, 720, .73),
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000001002', 18800, 1200, 6200, 6100, 2440, 610, .18),
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000001003', 2600, 380, 900, 4500, 1800, 450, .82),
  ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000001001', 6400, 460, 3200, 8160, 2720, 680, .38),
  ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000001004', 9600, 430, 1300, 3720, 1240, 310, .09),
  ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000001001', 1600, 250, 400, 5040, 1680, 420, .91),
  ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000001003', 980, 180, 250, 2100, 840, 210, .94)
on conflict (warehouse_id, product_id) do update set quantity = excluded.quantity, reserved = excluded.reserved, incoming = excluded.incoming, average_daily_demand = excluded.average_daily_demand, stockout_probability = excluded.stockout_probability;

insert into public.suppliers (id, organization_id, name, region, lead_time_days, minimum_order_quantity)
values
  ('00000000-0000-0000-0000-000000002001', '00000000-0000-0000-0000-000000000001', 'ACI Consumer Brands', 'Dhaka', 8, 240),
  ('00000000-0000-0000-0000-000000002002', '00000000-0000-0000-0000-000000000001', 'Meghna Group Foods', 'Chattogram', 10, 240),
  ('00000000-0000-0000-0000-000000002003', '00000000-0000-0000-0000-000000000001', 'PRAN-RFL Group', 'Rajshahi', 7, 240)
on conflict (id) do update set lead_time_days = excluded.lead_time_days;

insert into public.sentiment (organization_id, region, product_id, sentiment_score, demand_signal, confidence, sentiment_change, sample_count, source)
values
  ('00000000-0000-0000-0000-000000000001', 'Dhaka', '00000000-0000-0000-0000-000000001001', .72, .84, .91, .18, 1840, 'synthetic-demo'),
  ('00000000-0000-0000-0000-000000000001', 'Chattogram', '00000000-0000-0000-0000-000000001001', .61, .68, .88, .06, 920, 'synthetic-demo'),
  ('00000000-0000-0000-0000-000000000001', 'Sylhet', '00000000-0000-0000-0000-000000001003', .48, .54, .82, -.12, 610, 'synthetic-demo');
