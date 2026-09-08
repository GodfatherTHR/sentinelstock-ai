export type EventEnvelope<TPayload> = {
  event_id: string;
  event_type: string;
  timestamp: string;
  source: string;
  schema_version: string;
  tenant_id?: string;
  payload: TPayload;
};

export type InventoryUpdatedPayload = {
  warehouse_id: string;
  product_id: string;
  quantity: number;
  reserved: number;
  incoming: number;
  movement_reference?: string;
};

export type ForecastGeneratedPayload = {
  warehouse_id: string;
  product_id: string;
  horizon_days: number;
  predicted_demand: number;
  lower_bound: number;
  upper_bound: number;
  confidence: number;
  model_name: string;
  model_version: string;
};

export type RestockRecommendedPayload = {
  decision_id: string;
  warehouse_id: string;
  product_id: string;
  recommended_quantity: number;
  supplier_id?: string;
  risk_score: number;
  confidence: number;
  approval_status: "pending" | "approved" | "rejected" | "executed";
};
