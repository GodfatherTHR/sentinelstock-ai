import { forecasts, inventory, recommendations, sentiment, shipments, suppliers, warehouses } from "./demo-data";
import type { Forecast, InventoryRow, Recommendation, Sentiment, Shipment, Supplier, Warehouse } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL;

async function get<T>(path: string, fallback: T): Promise<T> {
  if (!API) return fallback;
  try { const response = await fetch(`${API}/api${path}`, { cache: "no-store" }); if (!response.ok) return fallback; return await response.json() as T; } catch { return fallback; }
}

export const api = {
  warehouses: () => get<Warehouse[]>("/warehouses", warehouses),
  inventory: () => get<InventoryRow[]>("/inventory", inventory),
  forecasts: () => get<Forecast[]>("/forecasts", forecasts),
  sentiment: () => get<Sentiment[]>("/sentiment", sentiment),
  suppliers: () => get<Supplier[]>("/suppliers", suppliers),
  shipments: () => get<Shipment[]>("/shipments", shipments),
  recommendations: () => get<Recommendation[]>("/recommendations", recommendations),
  approve: async (id: string) => { if (API) { await fetch(`${API}/api/recommendations/${id}/approve`, { method: "POST", headers: { "X-Demo-Role": "procurement_manager" } }); } return id; },
  reject: async (id: string) => { if (API) { await fetch(`${API}/api/recommendations/${id}/reject`, { method: "POST", headers: { "X-Demo-Role": "procurement_manager" } }); } return id; },
};
