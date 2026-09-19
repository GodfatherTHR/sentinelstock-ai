import { getAccessToken, signOut } from "./supabase-browser";
import type {
  AgentAnswer,
  AuditEntry,
  CropIndex,
  Forecast,
  Health,
  InventoryRow,
  PurchaseOrderRow,
  Ready,
  Recommendation,
  RiskRow,
  SalesPoint,
  Sentiment,
  Shipment,
  SignalBundle,
  SimulationResult,
  Supplier,
  Vessel,
  Warehouse,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API) throw new Error("NEXT_PUBLIC_API_URL is not configured for this environment");
  const token = await getAccessToken();
  const response = await fetch(`${API}/api${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (response.status === 401) {
    // The session cookie can outlive the access token; clear it and send the operator back to sign-in.
    await signOut();
    if (typeof window !== "undefined") window.location.assign("/login");
    throw new Error("Session expired — please sign in again");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  ready: () => request<Ready>("/ready"),
  warehouses: () => request<Warehouse[]>("/warehouses"),
  inventory: () => request<InventoryRow[]>("/inventory"),
  forecasts: () => request<Forecast[]>("/forecasts"),
  sentiment: () => request<Sentiment[]>("/sentiment"),
  suppliers: () => request<Supplier[]>("/suppliers"),
  shipments: () => request<Shipment[]>("/shipments"),
  sales: (params: { days?: number; warehouse_id?: string; product_id?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.days) query.set("days", String(params.days));
    if (params.warehouse_id) query.set("warehouse_id", params.warehouse_id);
    if (params.product_id) query.set("product_id", params.product_id);
    const suffix = query.toString();
    return request<SalesPoint[]>(`/sales${suffix ? `?${suffix}` : ""}`);
  },
  vessels: () => request<Vessel[]>("/vessels"),
  signals: () => request<SignalBundle>("/signals"),
  recommendations: () => request<Recommendation[]>("/recommendations"),
  risk: () => request<RiskRow[]>("/risk"),
  purchaseOrders: () => request<PurchaseOrderRow[]>("/purchase-orders"),
  auditLog: () => request<AuditEntry[]>("/audit-log"),
  runForecast: () => request<{ rows_written: number }>("/forecast/run", { method: "POST" }),
  generateRecommendation: () => request<Recommendation>("/recommendations/generate", { method: "POST", body: JSON.stringify({}) }),
  approve: (id: string) => request<Recommendation>(`/recommendations/${id}/approve`, { method: "POST" }),
  reject: (id: string) => request<Recommendation>(`/recommendations/${id}/reject`, { method: "POST" }),
  createPurchaseOrder: (decisionId: string) =>
    request<PurchaseOrderRow>("/purchase-orders", { method: "POST", body: JSON.stringify({ decision_id: decisionId }) }),
  simulate: (body: { demand_delta_percent: number; lead_time_delta_days: number; crop_delta_percent: number; sentiment_delta_percent: number }) =>
    request<SimulationResult>("/simulation", { method: "POST", body: JSON.stringify(body) }),
  ask: (query: string) => request<AgentAnswer>("/agent/ask", { method: "POST", body: JSON.stringify({ query }) }),
  cropHealth: (bundle: SignalBundle) => bundle.crop_health as CropIndex[],
  forecastsFor: (rows: Forecast[], warehouseId: string, productId: string) =>
    rows.filter((row) => row.warehouse_id === warehouseId && row.product_id === productId),
};
