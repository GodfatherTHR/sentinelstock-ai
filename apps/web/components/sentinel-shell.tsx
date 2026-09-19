"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, Bell, Boxes, Check, ChevronRight, CircleHelp,
  ClipboardCheck, CloudSun, Database, FileClock, Gauge, GitBranch, Leaf, LogOut, MapPin, MousePointerClick,
  PackageCheck, PanelLeftClose, PanelLeftOpen, Play, Radio, RefreshCw, Satellite, ShipWheel, ShieldCheck,
  SlidersHorizontal, Sparkles, Truck, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { getSessionEmail, signOut } from "@/lib/supabase-browser";
import type {
  AgentAnswer,
  AuditEntry, CropIndex, Forecast, InventoryRow, PurchaseOrderRow, Recommendation, RiskRow, SalesPoint, Sentiment,
  Shipment, SignalBundle, SimulationResult, Supplier, Vessel, Warehouse,
} from "@/lib/types";

type SectionKey = "dashboard" | "warehouses" | "inventory" | "forecasts" | "sentiment" | "logistics" | "suppliers" | "purchase-orders" | "ai-recommendations" | "risk" | "signals" | "simulation" | "audit-log" | "settings";

const nav: { key: SectionKey; label: string; icon: typeof Gauge; group: string }[] = [
  { key: "dashboard", label: "Network pulse", icon: Gauge, group: "Operations" },
  { key: "warehouses", label: "Warehouses", icon: Boxes, group: "Operations" },
  { key: "inventory", label: "Inventory", icon: PackageCheck, group: "Operations" },
  { key: "forecasts", label: "Forecasts", icon: BarChart3, group: "Operations" },
  { key: "sentiment", label: "Sentiment", icon: Sparkles, group: "Operations" },
  { key: "logistics", label: "Logistics", icon: Truck, group: "Operations" },
  { key: "suppliers", label: "Suppliers", icon: GitBranch, group: "Operations" },
  { key: "purchase-orders", label: "Purchase orders", icon: ClipboardCheck, group: "Procurement" },
  { key: "ai-recommendations", label: "AI recommendations", icon: Sparkles, group: "Procurement" },
  { key: "risk", label: "Risk center", icon: ShieldCheck, group: "Procurement" },
  { key: "simulation", label: "Simulation", icon: SlidersHorizontal, group: "Decision lab" },
  { key: "signals", label: "External signals", icon: Database, group: "Decision lab" },
  { key: "audit-log", label: "Audit log", icon: FileClock, group: "Decision lab" },
  { key: "settings", label: "Settings", icon: CloudSun, group: "Decision lab" },
];

function formatNumber(value: number) { return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value); }
function formatCurrency(value: number) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value); }
function formatDateTime(value: string | null) { if (!value) return "—"; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
function riskClass(risk: string) { return risk === "CRITICAL" ? "border-coral/30 bg-coral/10 text-coral" : risk === "HIGH" ? "border-orange/30 bg-orange/10 text-orange" : risk === "MEDIUM" ? "border-yellow-200/20 bg-yellow-200/10 text-yellow-100" : "border-mint/25 bg-mint/10 text-mint"; }

function RiskBadge({ risk }: { risk: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 text-[10px] font-semibold tracking-[.12em] ${riskClass(risk)}`}><span className="status-dot" style={{ background: risk === "CRITICAL" ? "#FF6B62" : risk === "HIGH" ? "#FF9C58" : risk === "MEDIUM" ? "#D7D885" : "#8BE4C0" }} />{risk}</span>;
}

function MetricCard({ label, value, detail, tone = "ice", icon: Icon }: { label: string; value: string; detail: string; tone?: "ice" | "mint" | "orange" | "coral"; icon: typeof Activity }) {
  const toneMap = { ice: "text-ice", mint: "text-mint", orange: "text-orange", coral: "text-coral" };
  return <div className="panel relative overflow-hidden rounded-sm p-4"><div className="flex items-start justify-between"><span className="eyebrow">{label}</span><Icon size={15} className={toneMap[tone]} strokeWidth={1.6} /></div><div className="mt-4 flex items-end justify-between"><span className="mono text-[28px] leading-none tracking-[-.05em] text-ink">{value}</span></div><p className="mt-2 text-xs text-muted">{detail}</p></div>;
}

function PanelHeader({ title, eyebrow, action }: { title: string; eyebrow: string; action?: React.ReactNode }) {
  return <div className="flex items-start justify-between border-b border-seam px-4 py-4"><div><span className="eyebrow">{eyebrow}</span><h3 className="mt-1 text-sm font-medium text-ink">{title}</h3></div>{action}</div>;
}

function EmptyState({ title, copy, action }: { title: string; copy: string; action?: React.ReactNode }) {
  return <div className="flex min-h-[180px] flex-col items-center justify-center gap-2 p-8 text-center"><div className="rounded-full border border-seam p-3 text-ice"><CircleHelp size={18} /></div><h3 className="text-sm font-medium text-ink">{title}</h3><p className="max-w-md text-xs leading-6 text-muted">{copy}</p>{action}</div>;
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <th className={`px-4 py-3 text-[10px] font-semibold uppercase tracking-[.12em] text-muted ${align === "right" ? "text-right" : "text-left"}`}>{children}</th>;
}

function Td({ children, align = "left", mono = false }: { children: React.ReactNode; align?: "left" | "right"; mono?: boolean }) {
  return <td className={`px-4 py-3 text-xs text-ink ${align === "right" ? "text-right" : ""} ${mono ? "mono text-[11px]" : ""}`}>{children}</td>;
}

function WarehouseMap({ data, onSelect }: { data: Warehouse[]; onSelect: (id: string) => void }) {
  const slots = [{ left: "59%", top: "57%" }, { left: "79%", top: "72%" }, { left: "42%", top: "33%" }, { left: "78%", top: "26%" }, { left: "31%", top: "64%" }, { left: "55%", top: "17%" }];
  return (
    <div className="panel relative min-h-[330px] overflow-hidden rounded-sm">
      <div className="absolute inset-0 map-grid opacity-60" />
      <div className="absolute left-5 top-5 flex items-center gap-2"><MapPin size={14} className="text-ice" /><span className="eyebrow">Warehouse signal map</span><span className="rounded-full border border-seam px-2 py-0.5 text-[9px] text-muted">DATABASE READ</span></div>
      <svg viewBox="0 0 500 300" className="absolute inset-0 h-full w-full opacity-35" aria-hidden="true"><path d="M178 94 C240 104 260 142 295 172 S380 197 401 219" fill="none" stroke="#8CD8EA" strokeDasharray="4 8" /><path d="M295 172 C320 144 363 104 392 82" fill="none" stroke="#FF9C58" strokeDasharray="3 10" /></svg>
      {data.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">No warehouses returned for this organization.</div>}
      {data.map((warehouse, index) => (
        <button key={warehouse.id} className="absolute -translate-x-1/2 -translate-y-1/2 text-left transition-transform hover:scale-105" style={slots[index % slots.length]} onClick={() => onSelect(warehouse.id)} aria-label={`Open ${warehouse.name}`}>
          <span className="relative flex h-9 w-9 items-center justify-center rounded-full border" style={{ borderColor: warehouse.risk_level === "CRITICAL" ? "rgba(255,107,98,.7)" : warehouse.risk_level === "HIGH" ? "rgba(255,156,88,.7)" : "rgba(139,228,192,.65)", background: "rgba(7,16,20,.88)" }}>
            <span className="absolute h-2.5 w-2.5 rounded-full" style={{ background: warehouse.risk_level === "CRITICAL" ? "#FF6B62" : warehouse.risk_level === "HIGH" ? "#FF9C58" : "#8BE4C0" }} />
          </span>
          <span className="mt-2 block min-w-[112px] rounded-sm border border-seam bg-shell/85 px-2 py-1.5 backdrop-blur"><span className="block text-[10px] font-medium text-ink">{warehouse.name}</span><span className="mono mt-1 block text-[10px] text-muted">{Math.round(warehouse.utilization * 100)}% filled · <span className={warehouse.risk_level === "LOW" ? "text-mint" : warehouse.risk_level === "CRITICAL" ? "text-coral" : "text-orange"}>{warehouse.risk_level}</span></span></span>
        </button>
      ))}
      <div className="absolute bottom-4 left-5 flex items-center gap-4 text-[10px] text-muted"><span className="flex items-center gap-1.5"><span className="status-dot bg-mint" />stable</span><span className="flex items-center gap-1.5"><span className="status-dot bg-orange" />watch</span><span className="flex items-center gap-1.5"><span className="status-dot bg-coral" />critical</span></div>
    </div>
  );
}

function RecommendationRow({ recommendation, onSelect, onApprove, onReject }: { recommendation: Recommendation; onSelect: (value: Recommendation) => void; onApprove: (id: string) => void; onReject: (id: string) => void }) {
  return (
    <div className="group border-b border-seam/70 px-4 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <button className="min-w-0 text-left" onClick={() => onSelect(recommendation)}>
          <div className="flex items-center gap-2"><RiskBadge risk={recommendation.urgency} /><span className="mono text-[10px] text-muted">{recommendation.id}</span></div>
          <p className="mt-2 truncate text-sm font-medium text-ink group-hover:text-ice">{recommendation.product_name}</p>
          <p className="mt-1 text-xs text-muted">{recommendation.warehouse_name} · {recommendation.supplier_name ?? "no supplier"}</p>
        </button>
        <div className="text-right"><div className="mono text-base text-ink">{formatNumber(recommendation.recommended_quantity)}</div><div className="text-[10px] uppercase tracking-[.12em] text-muted">units</div></div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[11px] text-muted">{recommendation.days_of_inventory.toFixed(1)}d coverage <span className="text-seam">·</span> {Math.round(recommendation.confidence * 100)}% confidence</span>
        {recommendation.approval_status === "pending" ? (
          <div className="flex items-center gap-2"><button className="rounded-sm border border-seam px-2 py-1 text-[10px] font-medium text-muted transition-colors hover:border-coral/40 hover:text-coral" onClick={() => onReject(recommendation.id)}>Reject</button><button className="rounded-sm bg-mint px-2.5 py-1 text-[10px] font-semibold text-shell transition-colors hover:bg-white" onClick={() => onApprove(recommendation.id)}><Check size={12} className="mr-1 inline" />Approve</button></div>
        ) : (
          <span className={`inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[.1em] ${recommendation.approval_status === "approved" ? "text-mint" : "text-coral"}`}><Check size={13} />{recommendation.approval_status}</span>
        )}
      </div>
    </div>
  );
}

function Drawer({ recommendation, onClose, onApprove, onReject, onCreateOrder, busy }: { recommendation: Recommendation; onClose: () => void; onApprove: (id: string) => void; onReject: (id: string) => void; onCreateOrder: (id: string) => void; busy: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label="Recommendation evidence">
      <div className="h-full w-full max-w-[520px] overflow-y-auto border-l border-seam bg-[#0b191e] p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <div><span className="eyebrow">Recommendation dossier</span><h2 className="mt-2 text-xl font-medium tracking-[-.02em] text-ink">{recommendation.product_name}</h2><p className="mt-1 text-sm text-muted">{recommendation.warehouse_name} · {recommendation.id}</p></div>
          <button className="rounded-sm border border-seam p-2 text-muted hover:text-ink" onClick={onClose} aria-label="Close recommendation"><X size={17} /></button>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-2">
          <div className="panel rounded-sm p-3"><span className="eyebrow">Proposed quantity</span><div className="mono mt-2 text-2xl text-ink">{formatNumber(recommendation.recommended_quantity)}</div><p className="mt-1 text-xs text-muted">{formatCurrency(recommendation.expected_cost)} expected spend</p></div>
          <div className="panel rounded-sm p-3"><span className="eyebrow">Risk posture</span><div className="mt-2"><RiskBadge risk={recommendation.urgency} /></div><p className="mt-2 text-xs text-muted">{Math.round(recommendation.expected_stockout_probability * 100)}% expected stockout probability</p></div>
        </div>
        <section className="mt-7">
          <div className="mb-3 flex items-center justify-between"><span className="eyebrow">Decision explanation</span><span className="mono text-[10px] text-muted">evidence / 07</span></div>
          <div className="space-y-2">{([["WHAT", recommendation.explanation.what], ["HOW MUCH", recommendation.explanation.how_much], ["WHEN", recommendation.explanation.when], ["FROM WHERE", recommendation.explanation.from_where], ["WHY", recommendation.explanation.why], ["RISK", recommendation.explanation.risk], ["CONFIDENCE", recommendation.explanation.confidence]] as const).map(([label, text]) => <div key={label} className="border-l border-ice/20 py-1 pl-3"><div className="eyebrow text-ice/70">{label}</div><p className="mt-1 text-sm leading-6 text-ink/80">{text}</p></div>)}</div>
        </section>
        <section className="mt-7"><span className="eyebrow">Observed drivers</span><div className="mt-3 flex flex-wrap gap-2">{recommendation.drivers.map((driver) => <span key={driver} className="rounded-sm border border-ice/20 bg-ice/5 px-2.5 py-1.5 text-[10px] text-ice">{driver.replaceAll("_", " ")}</span>)}</div></section>
        <div className="mt-8 flex gap-2 border-t border-seam pt-5">
          {recommendation.approval_status === "pending" ? (
            <>
              <button className="flex-1 rounded-sm border border-seam px-3 py-2.5 text-xs font-medium text-muted hover:border-coral/50 hover:text-coral" onClick={() => onReject(recommendation.id)}>Reject</button>
              <button disabled={busy} className="flex-1 rounded-sm bg-mint px-3 py-2.5 text-xs font-semibold text-shell hover:bg-white disabled:opacity-60" onClick={() => { onApprove(recommendation.id); onClose(); }}>Approve recommendation</button>
            </>
          ) : (
            <button disabled={busy || recommendation.approval_status !== "approved"} className="flex-1 rounded-sm bg-ice px-3 py-2.5 text-xs font-semibold text-shell hover:bg-white disabled:opacity-50" onClick={() => { onCreateOrder(recommendation.id); onClose(); }}>Create purchase order</button>
          )}
        </div>
        <p className="mt-4 text-center text-[10px] leading-5 text-muted">Approval writes an immutable decision record and an audit entry in Supabase. Purchase orders remain a separate role-gated action.</p>
      </div>
    </div>
  );
}

function SimulationPanel({ onClose, onRun, result, running, error }: { onClose: () => void; onRun: (input: { demand: number; lead: number; crop: number }) => void; result: SimulationResult | null; running: boolean; error: string | null }) {
  const [demand, setDemand] = useState(20);
  const [lead, setLead] = useState(0);
  const [crop, setCrop] = useState(0);
  const rows: [string, string, string][] = result
    ? [
        ["Inventory units", formatNumber(result.baseline.inventory_units), formatNumber(result.scenario.inventory_units)],
        ["Stockout locations", formatNumber(result.baseline.stockout_count), formatNumber(result.scenario.stockout_count)],
        ["Orders required", result.baseline.orders_required.toFixed(1), result.scenario.orders_required.toFixed(1)],
        ["Expected cost", formatCurrency(result.baseline.cost), formatCurrency(result.scenario.cost)],
        ["Service level", `${Math.round(result.baseline.service_level * 100)}%`, `${Math.round(result.scenario.service_level * 100)}%`],
      ]
    : [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="panel w-full max-w-3xl rounded-sm bg-[#0b191e] p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <div><span className="eyebrow">Decision lab / scenario simulator</span><h2 className="mt-2 text-xl font-medium text-ink">Stress-test the live network</h2><p className="mt-1 text-sm text-muted">Baseline comes from current inventory and recommendations; the simulator never mutates data.</p></div>
          <button className="rounded-sm border border-seam p-2 text-muted hover:text-ink" onClick={onClose} aria-label="Close simulator"><X size={17} /></button>
        </div>
        <div className="mt-6 grid gap-6 md:grid-cols-[1fr_1.2fr]">
          <div className="space-y-5">
            {([["Demand change", demand, setDemand, "%", -20, 100], ["Supplier lead time", lead, setLead, " days", -3, 20], ["Crop production", crop, setCrop, "%", -40, 20]] as const).map(([label, value, setter, suffix, min, max]) => (
              <label key={label} className="block"><div className="flex justify-between text-xs"><span className="text-ink">{label}</span><span className="mono text-ice">{value > 0 ? "+" : ""}{value}{suffix}</span></div><input className="mt-2 w-full accent-[#8BE4C0]" type="range" min={min} max={max} value={value} onChange={(event) => setter(Number(event.target.value))} /></label>
            ))}
          </div>
          <div className="panel rounded-sm p-4">
            <div className="mb-4 flex items-center justify-between"><span className="eyebrow">BASELINE vs SCENARIO</span><span className="text-[10px] text-muted">deterministic phase 1</span></div>
            {result ? (
              <div className="grid grid-cols-2 gap-3">{rows.map(([label, base, next]) => <div key={label} className="border-b border-seam/70 pb-3"><div className="text-[10px] text-muted">{label}</div><div className="mt-2 flex items-baseline gap-2"><span className="mono text-lg text-muted">{base}</span><ChevronRight size={13} className="text-seam" /><span className={`mono text-lg ${next === base ? "text-ink" : "text-orange"}`}>{next}</span></div></div>)}</div>
            ) : (
              <p className="text-xs leading-6 text-muted">Run the scenario to compare the live baseline against the stressed case. {error && <span className="text-orange">{error}</span>}</p>
            )}
            <div className="mt-5 border-l border-orange/60 pl-3 text-xs leading-5 text-muted">{result?.assumptions[1] ?? "Crop and sentiment changes are supply and demand features, not exact inventory predictions."}</div>
          </div>
        </div>
        <div className="mt-6 flex justify-end"><button disabled={running} className="inline-flex items-center gap-2 rounded-sm bg-ice px-4 py-2.5 text-xs font-semibold text-shell hover:bg-white disabled:opacity-60" onClick={() => onRun({ demand, lead, crop })}><Play size={13} />{running ? "Running…" : "Run scenario"}</button></div>
      </div>
    </div>
  );
}

export function SentinelShell({ initialSection = "dashboard" }: { initialSection?: string }) {
  const validSection = (nav.some((item) => item.key === initialSection) ? initialSection : "dashboard") as SectionKey;
  const [section, setSection] = useState<SectionKey>(validSection);
  const [collapsed, setCollapsed] = useState(false);
  const [selectedWarehouse, setSelectedWarehouse] = useState("all");
  const [selectedRecommendation, setSelectedRecommendation] = useState<Recommendation | null>(null);
  const [simulationOpen, setSimulationOpen] = useState(false);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [simulationRunning, setSimulationRunning] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [askQuery, setAskQuery] = useState("");
  const [askAnswer, setAskAnswer] = useState<AgentAnswer | null>(null);
  const [askLoading, setAskLoading] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [inventory, setInventoryRows] = useState<InventoryRow[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [sentimentRows, setSentimentRows] = useState<Sentiment[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [signals, setSignals] = useState<SignalBundle | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [riskRows, setRiskRows] = useState<RiskRow[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrderRow[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [salesSeries, setSalesSeries] = useState<SalesPoint[]>([]);

  function notify(message: string) { setToast(message); window.setTimeout(() => setToast(null), 3600); }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const problems: string[] = [];
    async function settle<T>(promise: Promise<T>, fallback: T): Promise<T> {
      try { return await promise; } catch (issue) { problems.push(issue instanceof Error ? issue.message : String(issue)); return fallback; }
    }
    const [nextWarehouses, nextInventory, nextForecasts, nextSentiment, nextSuppliers, nextShipments, nextVessels, nextSignals, nextRecommendations, nextRisk, nextOrders, nextAudit] = await Promise.all([
      settle(api.warehouses(), []), settle(api.inventory(), []), settle(api.forecasts(), []), settle(api.sentiment(), []),
      settle(api.suppliers(), []), settle(api.shipments(), []), settle(api.vessels(), []), settle(api.signals(), null),
      settle(api.recommendations(), []), settle(api.risk(), []), settle(api.purchaseOrders(), []), settle(api.auditLog(), []),
    ]);
    setWarehouses(nextWarehouses); setInventoryRows(nextInventory); setForecasts(nextForecasts); setSentimentRows(nextSentiment);
    setSuppliers(nextSuppliers); setShipments(nextShipments); setVessels(nextVessels); setSignals(nextSignals);
    setRecommendations(nextRecommendations); setRiskRows(nextRisk); setPurchaseOrders(nextOrders); setAuditEntries(nextAudit);
    setWarnings([...new Set(problems)]);
    if (problems.length === 12) {
      setError(
        `Cannot reach the API at ${process.env.NEXT_PUBLIC_API_URL ?? "NEXT_PUBLIC_API_URL"}. Start it with: py -3 -m uvicorn app.main:app --app-dir services/api --port 8000`,
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => { void load(); void getSessionEmail().then(setEmail); }, [load]);

  const visibleInventory = useMemo(() => (selectedWarehouse === "all" ? inventory : inventory.filter((row) => row.warehouse_id === selectedWarehouse)), [inventory, selectedWarehouse]);
  const pendingRecommendations = recommendations.filter((row) => row.approval_status === "pending");
  const totalValue = warehouses.reduce((sum, warehouse) => sum + warehouse.inventory_value, 0);
  const riskInventory = visibleInventory.filter((row) => row.inventory_risk === "HIGH" || row.inventory_risk === "CRITICAL");
  const focusInventory = useMemo(() => [...inventory].sort((a, b) => b.stockout_probability - a.stockout_probability)[0], [inventory]);
  const focusForecast = useMemo(() => {
    if (!focusInventory) return null;
    return forecasts.find((row) => row.warehouse_id === focusInventory.warehouse_id && row.product_id === focusInventory.product_id && row.horizon === "7d") ?? null;
  }, [focusInventory, forecasts]);
  const chartData = useMemo(
    () => salesSeries.map((point) => ({ day: point.day.slice(5), quantity: Math.round(point.quantity) })),
    [salesSeries],
  );

  useEffect(() => {
    if (!focusInventory) return;
    void api
      .sales({ days: 14, warehouse_id: focusInventory.warehouse_id, product_id: focusInventory.product_id })
      .then(setSalesSeries)
      .catch(() => setSalesSeries([]));
  }, [focusInventory]);

  async function handleApprove(id: string) {
    setBusy(true);
    try { const updated = await api.approve(id); setRecommendations((rows) => rows.map((row) => (row.id === id ? updated : row))); setSelectedRecommendation(updated); notify("Approved · decision and audit rows written to Supabase"); await load(); }
    catch (issue) { notify(issue instanceof Error ? issue.message : "Approval failed"); }
    finally { setBusy(false); }
  }

  async function handleReject(id: string) {
    setBusy(true);
    try { const updated = await api.reject(id); setRecommendations((rows) => rows.map((row) => (row.id === id ? updated : row))); setSelectedRecommendation(updated); notify("Rejected · decision recorded"); await load(); }
    catch (issue) { notify(issue instanceof Error ? issue.message : "Rejection failed"); }
    finally { setBusy(false); }
  }

  async function handleCreateOrder(id: string) {
    setBusy(true);
    try { const order = await api.createPurchaseOrder(id); notify(`Purchase order ${order.id.slice(0, 8)} created for ${order.supplier_name}`); await load(); setSection("purchase-orders"); }
    catch (issue) { notify(issue instanceof Error ? issue.message : "Purchase order failed"); }
    finally { setBusy(false); }
  }

  async function handleRunForecast() {
    setBusy(true);
    try { const result = await api.runForecast(); notify(`Baseline forecast stored · ${result.rows_written} rows`); await load(); }
    catch (issue) { notify(issue instanceof Error ? issue.message : "Forecast run failed"); }
    finally { setBusy(false); }
  }

  async function handleAsk(question: string) {
    if (!question.trim()) return;
    setAskLoading(true);
    try { setAskAnswer(await api.ask(question.trim())); }
    catch (issue) { notify(issue instanceof Error ? issue.message : "Ask failed"); }
    finally { setAskLoading(false); }
  }

  async function handleSimulation(input: { demand: number; lead: number; crop: number }) {
    setSimulationRunning(true);
    try {
      const result = await api.simulate({ demand_delta_percent: input.demand, lead_time_delta_days: input.lead, crop_delta_percent: input.crop, sentiment_delta_percent: 0 });
      setSimulation(result);
    } catch (issue) { notify(issue instanceof Error ? issue.message : "Simulation failed"); }
    finally { setSimulationRunning(false); }
  }

  function goTo(key: SectionKey) { setSection(key); window.history.replaceState(null, "", key === "dashboard" ? "/" : `/${key}`); }

  if (loading && warehouses.length === 0 && inventory.length === 0) {
    return <div className="flex min-h-screen items-center justify-center bg-shell"><div className="panel rounded-sm px-6 py-5 text-center"><div className="mono text-[11px] uppercase tracking-[.2em] text-mint">SentinelStock</div><p className="mt-2 text-sm text-muted">Loading tenant data from Supabase…</p></div></div>;
  }

  return (
    <div className="min-h-screen bg-shell text-ink">
      <aside className={`fixed inset-y-0 left-0 z-30 hidden border-r border-seam/80 bg-[#09161A] transition-all lg:block ${collapsed ? "w-[76px]" : "w-[240px]"}`}>
        <div className="flex h-16 items-center border-b border-seam/80 px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-sm border border-mint/35 bg-mint/10 text-mint"><Radio size={17} /></div>
          {!collapsed && <div className="ml-3"><div className="text-[13px] font-semibold tracking-[-.02em] text-ink">SentinelStock</div><div className="mono text-[9px] uppercase tracking-[.14em] text-muted">AI / OPS CONSOLE</div></div>}
        </div>
        <div className="px-3 py-5">
          {["Operations", "Procurement", "Decision lab"].map((group) => (
            <div key={group} className="mb-5">
              {!collapsed && <div className="eyebrow mb-2 px-2">{group}</div>}
              {nav.filter((item) => item.group === group).map((item) => {
                const Icon = item.icon; const active = section === item.key;
                return <button key={item.key} onClick={() => goTo(item.key)} className={`mb-1 flex w-full items-center rounded-sm px-2.5 py-2.5 text-left text-xs transition-colors ${active ? "bg-ice/10 text-ice" : "text-muted hover:bg-white/[.03] hover:text-ink"}`} title={collapsed ? item.label : undefined}><Icon size={15} strokeWidth={active ? 2 : 1.6} />{!collapsed && <span className="ml-3">{item.label}</span>}{active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-ice" />}</button>;
              })}
            </div>
          ))}
        </div>
        <div className="absolute bottom-0 left-0 right-0 border-t border-seam/80 p-3">
          <button className="flex w-full items-center rounded-sm px-2.5 py-2.5 text-left text-xs text-muted hover:bg-white/[.03] hover:text-ink" onClick={() => setCollapsed((value) => !value)}>{collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />} {!collapsed && <span className="ml-3">Collapse rail</span>}</button>
        </div>
      </aside>
      <main className={`min-h-screen transition-all ${collapsed ? "lg:pl-[76px]" : "lg:pl-[240px]"}`}>
        <header className="sticky top-0 z-20 border-b border-seam/80 bg-shell/90 backdrop-blur">
          <div className="flex h-16 items-center justify-between px-5 lg:px-8">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-sm border border-mint/35 bg-mint/10 text-mint lg:hidden"><Radio size={16} /></div>
              <div><div className="eyebrow">{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "2-digit", month: "short", year: "numeric" })}</div><h1 className="mt-1 text-base font-medium text-ink">{section === "dashboard" ? "Network pulse" : nav.find((item) => item.key === section)?.label}</h1></div>
            </div>
            <div className="flex items-center gap-2">
              <button className="hidden items-center gap-2 rounded-sm border border-seam px-3 py-2 text-[11px] text-muted hover:border-ice/30 hover:text-ink md:flex" onClick={() => { setSection("simulation"); setSimulationOpen(true); }}><SlidersHorizontal size={13} />Simulate scenario</button>
              <span className="hidden items-center gap-2 rounded-sm border border-mint/20 bg-mint/5 px-2.5 py-2 text-[10px] font-medium text-mint sm:flex"><span className="status-dot bg-mint" />Supabase live</span>
              <button className="rounded-sm border border-seam p-2 text-muted hover:text-ink" onClick={() => void load()} aria-label="Refresh data"><RefreshCw size={15} className={loading ? "animate-spin" : ""} /></button>
              <button className="rounded-sm border border-seam p-2 text-muted hover:text-ink" aria-label="Notifications"><Bell size={16} /></button>
              <div className="ml-1 hidden text-right sm:block"><div className="text-[11px] text-ink">{email ?? "operator"}</div><div className="mono text-[9px] uppercase tracking-[.12em] text-muted">RLS session</div></div>
              <button className="rounded-sm border border-seam p-2 text-muted hover:border-coral/40 hover:text-coral" aria-label="Sign out" onClick={() => void signOut().then(() => window.location.assign("/login"))}><LogOut size={15} /></button>
            </div>
          </div>
        </header>

        <div className="min-h-[calc(100vh-64px)] bg-shell px-5 py-6 lg:px-8 lg:py-8">
          {error && <div className="mb-4 rounded-sm border border-coral/30 bg-coral/10 px-4 py-3 text-xs text-coral">{error}</div>}
          {warnings.length > 0 && !error && <div className="mb-4 rounded-sm border border-orange/25 bg-orange/10 px-4 py-3 text-[11px] text-orange">{warnings.length} read(s) returned an error: {warnings.slice(0, 2).join(" · ")}</div>}

          {section === "dashboard" && (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-end">
                <div>
                  <div className="flex items-center gap-2"><span className="eyebrow">Network overview</span>{pendingRecommendations.length > 0 && <span className="rounded-sm border border-orange/25 bg-orange/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[.12em] text-orange">{pendingRecommendations.length} actions need review</span>}</div>
                  <h2 className="mt-2 max-w-xl text-2xl font-medium tracking-[-.04em] text-ink md:text-3xl">{riskInventory.length > 0 ? `${riskInventory.length} SKU${riskInventory.length === 1 ? "" : "s"} inside the risk envelope.` : "All SKUs are outside the risk envelope."}<br /><span className="text-muted">{warehouses.length} warehouse nodes connected to Supabase.</span></h2>
                </div>
                <div className="flex items-center gap-2">
                  <label className="relative">
                    <span className="sr-only">Filter warehouse</span>
                    <select value={selectedWarehouse} onChange={(event) => setSelectedWarehouse(event.target.value)} className="appearance-none rounded-sm border border-seam bg-panel py-2.5 pl-3 pr-8 text-xs text-ink outline-none focus:border-ice/50"><option value="all">All warehouses</option>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select>
                    <ChevronRight size={14} className="pointer-events-none absolute right-2 top-2.5 rotate-90 text-muted" />
                  </label>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <MetricCard label="Inventory value" value={formatCurrency(totalValue)} detail={`${inventory.length} warehouse × SKU rows priced at product unit cost`} tone="ice" icon={Boxes} />
                <MetricCard label="Stockout exposure" value={`${riskInventory.length} SKUs`} detail="Above the 50% probability threshold from the policy model" tone="coral" icon={AlertTriangle} />
                <MetricCard label="Pending approvals" value={formatNumber(pendingRecommendations.length)} detail={`${formatCurrency(pendingRecommendations.reduce((sum, row) => sum + row.expected_cost, 0))} of proposed spend`} tone="mint" icon={ClipboardCheck} />
                <MetricCard label="Inbound shipments" value={formatNumber(shipments.length)} detail={`${shipments.filter((row) => row.delay_days > 0).length} running late against plan`} tone="orange" icon={Truck} />
                <MetricCard label="Tracked vessels" value={formatNumber(vessels.length)} detail="Live AIS snapshot stored by the connectors" tone="ice" icon={ShipWheel} />
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-[1.45fr_1fr]">
                <WarehouseMap data={warehouses} onSelect={(id) => { setSelectedWarehouse(id); notify(`Filtered to ${warehouses.find((warehouse) => warehouse.id === id)?.name ?? "warehouse"}`); }} />
                <div className="panel rounded-sm p-5">
                  <div className="flex items-start justify-between">
                    <div><span className="eyebrow">Demand baseline</span><h3 className="mt-2 text-sm font-medium text-ink">{focusInventory ? `${focusInventory.product_name} · ${focusInventory.warehouse_name}` : "No inventory rows"}</h3></div>
                    {focusInventory && <span className={`flex items-center gap-1 text-[11px] ${focusInventory.stockout_probability > 0.5 ? "text-coral" : "text-mint"}`}>{focusInventory.stockout_probability > 0.5 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{Math.round(focusInventory.stockout_probability * 100)}% stockout</span>}
                  </div>
                  {chartData.length > 0 ? (
                    <>
                      <div className="mt-5 h-[170px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData} margin={{ left: -24, right: 3, top: 7, bottom: 0 }}>
                            <defs><linearGradient id="predictedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8CD8EA" stopOpacity={.24} /><stop offset="100%" stopColor="#8CD8EA" stopOpacity={0} /></linearGradient></defs>
                            <CartesianGrid stroke="#22434A" strokeDasharray="2 5" vertical={false} />
                            <XAxis dataKey="day" tick={{ fill: "#8EA7A6", fontSize: 9 }} axisLine={false} tickLine={false} />
                            <YAxis tick={{ fill: "#8EA7A6", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(value) => (Number(value) >= 1000 ? `${Math.round(Number(value) / 1000)}k` : String(Math.round(Number(value))))} />
                            <Tooltip contentStyle={{ background: "#0B191E", border: "1px solid #22434A", borderRadius: 2, fontSize: 11 }} labelStyle={{ color: "#8EA7A6" }} />
                            <Area type="monotone" dataKey="quantity" stroke="#8CD8EA" fill="url(#predictedFill)" strokeWidth={2} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-muted">
                        <span className="flex items-center gap-2"><span className="h-px w-5 bg-ice" />observed daily sales</span>
                        {focusForecast ? <span>7-day forecast <span className="mono text-mint">{formatNumber(focusForecast.predicted_demand)}</span> · {Math.round(focusForecast.confidence * 100)}% confidence</span> : null}
                        <span className="ml-auto mono text-mint">{focusForecast?.model_name ?? "no stored forecast"}</span>
                      </div>
                    </>
                  ) : (
                    <EmptyState title="No sales history for this SKU" copy="Demand charts read the sales table. Seed or sync sales rows, then run the forecast to store horizons." action={<button disabled={busy} className="mt-3 rounded-sm bg-ice px-3 py-2 text-[11px] font-semibold text-shell hover:bg-white disabled:opacity-60" onClick={() => void handleRunForecast()}>Run baseline forecast</button>} />
                  )}
                </div>
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_.75fr]">
                <div className="panel overflow-hidden rounded-sm">
                  <PanelHeader eyebrow="Action queue" title="Recommendations requiring review" action={<button className="flex items-center gap-1 text-[11px] text-ice hover:text-white" onClick={() => goTo("ai-recommendations")}>View queue <ChevronRight size={13} /></button>} />
                  {pendingRecommendations.slice(0, 4).map((recommendation) => <RecommendationRow key={recommendation.id} recommendation={recommendation} onSelect={setSelectedRecommendation} onApprove={(id) => void handleApprove(id)} onReject={(id) => void handleReject(id)} />)}
                  {pendingRecommendations.length === 0 && <EmptyState title="Nothing needs approval" copy="The policy model found no SKU inside the reorder envelope for this organization." />}
                </div>
                <div className="space-y-4">
                  <div className="panel rounded-sm p-5">
                    <div className="flex items-start justify-between"><div><span className="eyebrow">Regional sentiment</span><h3 className="mt-1 text-sm font-medium text-ink">Consumer signal watch</h3></div><Sparkles size={16} className="text-ice" /></div>
                    {sentimentRows.length > 0 ? (
                      <div className="mt-4 space-y-3">
                        {sentimentRows.slice(0, 3).map((item) => (
                          <div key={`${item.region}-${item.product_category}`} className="flex items-center justify-between">
                            <div><div className="text-xs text-ink">{item.region} <span className="text-muted">/ {item.product_category}</span></div><div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-seam"><div className="h-full rounded-full bg-ice" style={{ width: `${Math.max(item.sentiment_score, 0) * 100}%` }} /></div></div>
                            <div className="text-right"><div className={`mono text-xs ${item.sentiment_change >= 0 ? "text-mint" : "text-coral"}`}>{item.sentiment_change >= 0 ? "+" : ""}{Math.round(item.sentiment_change * 100)}%</div><div className="text-[10px] text-muted">{item.sample_count.toLocaleString()} samples</div></div>
                          </div>
                        ))}
                      </div>
                    ) : <p className="mt-4 text-xs text-muted">No sentiment rows for this organization yet.</p>}
                  </div>
                  <div className="panel rounded-sm p-5">
                    <div className="flex items-start justify-between"><div><span className="eyebrow">Maritime watch</span><h3 className="mt-1 text-sm font-medium text-ink">Live AIS traffic</h3></div><ShipWheel size={16} className="text-orange" /></div>
                    {vessels.length > 0 ? (
                      <div className="mt-3 space-y-3">
                        {vessels.slice(0, 4).map((vessel) => (
                          <div key={vessel.mmsi} className="flex items-center gap-3 border-t border-seam/70 pt-3 first:border-0 first:pt-0">
                            <div className={`rounded-sm p-2 ${vessel.speed_knots && vessel.speed_knots > 1 ? "bg-mint/10 text-mint" : "bg-orange/10 text-orange"}`}><Truck size={15} /></div>
                            <div className="min-w-0 flex-1"><div className="truncate text-xs text-ink">{vessel.name ?? `MMSI ${vessel.mmsi}`}</div><div className="mt-1 truncate text-[10px] text-muted">{vessel.destination ?? "destination unknown"} · {vessel.nav_status_label ?? "status unknown"}</div></div>
                            <div className="text-right"><div className="mono text-[11px] text-ink">{vessel.speed_knots?.toFixed(1) ?? "0.0"} kn</div><div className="text-[10px] text-muted">{formatDateTime(vessel.observed_at)}</div></div>
                          </div>
                        ))}
                      </div>
                    ) : <p className="mt-4 text-xs text-muted">No vessel positions stored yet. Run the maritime connector to populate AIS data.</p>}
                  </div>
                </div>
              </div>

              <div className="panel mt-4 rounded-sm">
                <PanelHeader eyebrow="Ask the console" title="Local tool router · cactus-needle 14 MB · no API cost" />
                <div className="p-4">
                  <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(event) => { event.preventDefault(); void handleAsk(askQuery); }}>
                    <input value={askQuery} onChange={(event) => setAskQuery(event.target.value)} placeholder="Which SKUs are at risk of stocking out?" className="flex-1 rounded-sm border border-seam bg-shell px-3 py-2.5 text-xs text-ink outline-none placeholder:text-muted/60 focus:border-ice/50" />
                    <button type="submit" disabled={askLoading} className="rounded-sm bg-ice px-4 py-2.5 text-[11px] font-semibold text-shell hover:bg-white disabled:opacity-60">{askLoading ? "Routing…" : "Ask"}</button>
                  </form>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {["Which SKUs are at risk of stocking out?", "What is still waiting for approval?", "Show me the wheat crop health", "Any vessels heading to a port?"].map((example) => (
                      <button key={example} type="button" className="rounded-sm border border-seam px-2.5 py-1.5 text-[10px] text-muted hover:border-ice/30 hover:text-ice" onClick={() => { setAskQuery(example); void handleAsk(example); }}>{example}</button>
                    ))}
                  </div>
                  {askAnswer && (
                    <div className="mt-4 border-t border-seam pt-4">
                      <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted">
                        <span className="mono rounded-sm border border-ice/25 bg-ice/5 px-2 py-1 text-ice">{askAnswer.tool ?? "no tool matched"}</span>
                        <span>confidence {askAnswer.confidence === null ? "n/a" : `${Math.round(askAnswer.confidence * 100)}%`}</span>
                        <span>{askAnswer.rows.length} rows</span>
                        <span className="mono">{askAnswer.model}</span>
                      </div>
                      <p className="mt-3 text-xs leading-6 text-ink">{askAnswer.summary}</p>
                      {askAnswer.reasoning ? <p className="mt-2 text-[10px] text-muted">router reasoning: {askAnswer.reasoning}</p> : null}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-4 flex flex-col items-start justify-between gap-3 border-t border-seam/70 pt-4 text-[10px] text-muted sm:flex-row sm:items-center">
                <div className="flex items-center gap-2"><Database size={13} className="text-ice" />Supabase read model: <span className="text-mint">{inventory.length} inventory rows · {forecasts.length} forecast rows · {signals?.summary.agricultural_observations ?? 0} agricultural observations</span></div>
                <div className="flex items-center gap-3"><button className="text-ice hover:text-white" onClick={() => goTo("signals")}>External signals</button><span>·</span><span>Last load <span className="mono text-ink">{new Date().toLocaleTimeString("en-GB")}</span></span></div>
              </div>
            </>
          )}

          {section === "warehouses" && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {warehouses.map((warehouse) => (
                <div key={warehouse.id} className="panel rounded-sm p-5">
                  <div className="flex items-start justify-between"><div><span className="eyebrow">{warehouse.region}</span><h3 className="mt-1 text-sm font-medium text-ink">{warehouse.name}</h3></div><RiskBadge risk={warehouse.risk_level} /></div>
                  <div className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><div className="text-muted">Utilization</div><div className="mono mt-1 text-lg text-ink">{Math.round(warehouse.utilization * 100)}%</div></div><div><div className="text-muted">Inventory value</div><div className="mono mt-1 text-lg text-ink">{formatCurrency(warehouse.inventory_value)}</div></div><div><div className="text-muted">Capacity</div><div className="mono mt-1 text-ink">{formatNumber(warehouse.capacity)}</div></div><div><div className="text-muted">Risk score</div><div className="mono mt-1 text-ink">{warehouse.risk_score.toFixed(2)}</div></div></div>
                  <button className="mt-4 flex w-full items-center justify-center gap-2 rounded-sm border border-seam px-3 py-2 text-[11px] text-muted hover:border-ice/30 hover:text-ice" onClick={() => { setSelectedWarehouse(warehouse.id); goTo("inventory"); }}><MousePointerClick size={13} />Open inventory slice</button>
                </div>
              ))}
              {warehouses.length === 0 && <div className="panel rounded-sm"><EmptyState title="No warehouses" copy="This organization has no warehouse rows visible to your role." /></div>}
            </div>
          )}

          {section === "inventory" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Inventory ledger" title={`${visibleInventory.length} warehouse × SKU rows`} action={<select value={selectedWarehouse} onChange={(event) => setSelectedWarehouse(event.target.value)} className="rounded-sm border border-seam bg-panel px-2 py-1.5 text-[11px] text-ink"><option value="all">All warehouses</option>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select>} />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] border-collapse">
                  <thead className="bg-white/[.02]"><tr><Th>SKU</Th><Th>Warehouse</Th><Th align="right">Quantity</Th><Th align="right">Available</Th><Th align="right">Daily demand</Th><Th align="right">Days cover</Th><Th align="right">Stockout</Th><Th>Risk</Th></tr></thead>
                  <tbody>
                    {visibleInventory.map((row) => (
                      <tr key={row.id} className="border-t border-seam/70">
                        <Td><div className="text-ink">{row.product_name}</div><div className="mono text-[10px] text-muted">{row.sku} · {row.category}</div></Td>
                        <Td>{row.warehouse_name}</Td>
                        <Td align="right" mono>{formatNumber(row.quantity)}</Td>
                        <Td align="right" mono>{formatNumber(row.available_inventory)}</Td>
                        <Td align="right" mono>{formatNumber(row.average_daily_demand)}</Td>
                        <Td align="right" mono>{row.days_of_inventory.toFixed(1)}</Td>
                        <Td align="right" mono>{Math.round(row.stockout_probability * 100)}%</Td>
                        <Td><RiskBadge risk={row.inventory_risk} /></Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {visibleInventory.length === 0 && <EmptyState title="No inventory rows" copy="Inventory is empty for this slice. Seed or sync inventory rows in Supabase to populate the ledger." />}
              </div>
            </div>
          )}

          {section === "forecasts" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Forecast workspace" title={`${forecasts.length} stored forecast rows`} action={<button disabled={busy} className="flex items-center gap-2 rounded-sm bg-ice px-3 py-2 text-[11px] font-semibold text-shell hover:bg-white disabled:opacity-60" onClick={() => void handleRunForecast()}><Play size={12} />{busy ? "Running…" : "Run baseline forecast"}</button>} />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] border-collapse">
                  <thead className="bg-white/[.02]"><tr><Th>Product</Th><Th>Horizon</Th><Th align="right">Predicted</Th><Th align="right">Lower</Th><Th align="right">Upper</Th><Th align="right">Confidence</Th><Th>Model</Th></tr></thead>
                  <tbody>
                    {forecasts.map((row) => (
                      <tr key={`${row.warehouse_id}-${row.product_id}-${row.horizon}`} className="border-t border-seam/70">
                        <Td>{row.product_name}</Td><Td mono>{row.horizon}</Td><Td align="right" mono>{formatNumber(row.predicted_demand)}</Td><Td align="right" mono>{formatNumber(row.lower_bound)}</Td><Td align="right" mono>{formatNumber(row.upper_bound)}</Td><Td align="right" mono>{Math.round(row.confidence * 100)}%</Td><Td mono>{row.model_name} {row.model_version}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {forecasts.length === 0 && <EmptyState title="No stored forecasts" copy="The baseline model multiplies average daily demand by the horizon and persists rows into the forecasts table under your session." action={<button disabled={busy} className="mt-3 rounded-sm bg-ice px-3 py-2 text-[11px] font-semibold text-shell hover:bg-white disabled:opacity-60" onClick={() => void handleRunForecast()}>Run baseline forecast</button>} />}
              </div>
            </div>
          )}

          {section === "sentiment" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Regional sentiment" title="Aggregated consumer signals" />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse">
                  <thead className="bg-white/[.02]"><tr><Th>Region</Th><Th>Category</Th><Th align="right">Score</Th><Th align="right">Change</Th><Th align="right">Demand signal</Th><Th align="right">Samples</Th><Th>Trend</Th></tr></thead>
                  <tbody>
                    {sentimentRows.map((row) => (
                      <tr key={`${row.region}-${row.product_category}`} className="border-t border-seam/70">
                        <Td>{row.region}</Td><Td>{row.product_category}</Td><Td align="right" mono>{row.sentiment_score.toFixed(2)}</Td><Td align="right" mono>{row.sentiment_change >= 0 ? "+" : ""}{row.sentiment_change.toFixed(2)}</Td><Td align="right" mono>{row.demand_signal.toFixed(2)}</Td><Td align="right" mono>{formatNumber(row.sample_count)}</Td><Td>{row.trend}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {sentimentRows.length === 0 && <EmptyState title="No sentiment rows" copy="Consumer signals are aggregated per region and category; none are stored for this organization yet." />}
              </div>
            </div>
          )}

          {section === "logistics" && (
            <div className="space-y-4">
              <div className="panel overflow-hidden rounded-sm">
                <PanelHeader eyebrow="Maritime intelligence" title={`${vessels.length} vessels with live AIS positions`} />
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[860px] border-collapse">
                    <thead className="bg-white/[.02]"><tr><Th>Vessel</Th><Th>Destination</Th><Th>Type</Th><Th align="right">Speed</Th><Th align="right">Course</Th><Th>Nav status</Th><Th>Observed</Th></tr></thead>
                    <tbody>
                      {vessels.map((vessel) => (
                        <tr key={vessel.mmsi} className="border-t border-seam/70">
                          <Td><div className="text-ink">{vessel.name ?? `MMSI ${vessel.mmsi}`}</div><div className="mono text-[10px] text-muted">MMSI {vessel.mmsi}{vessel.imo ? ` · IMO ${vessel.imo}` : ""}</div></Td>
                          <Td mono>{vessel.destination ?? "—"}</Td><Td>{vessel.ship_type_label ?? "—"}</Td><Td align="right" mono>{vessel.speed_knots?.toFixed(1) ?? "—"}</Td><Td align="right" mono>{vessel.course_degrees?.toFixed(0) ?? "—"}</Td><Td>{vessel.nav_status_label ?? "—"}</Td><Td mono>{formatDateTime(vessel.observed_at)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {vessels.length === 0 && <EmptyState title="No AIS data" copy="Run `python -m app.worker maritime` in services/connectors to snapshot vessels and positions from Digitraffic." />}
                </div>
              </div>
              <div className="panel overflow-hidden rounded-sm">
                <PanelHeader eyebrow="Inbound shipments" title={`${shipments.length} shipment rows`} />
                {shipments.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] border-collapse">
                      <thead className="bg-white/[.02]"><tr><Th>Supplier</Th><Th>Destination</Th><Th>Vessel</Th><Th>ETA</Th><Th>Status</Th><Th align="right">Delay</Th><Th>Source</Th></tr></thead>
                      <tbody>{shipments.map((row) => <tr key={row.id} className="border-t border-seam/70"><Td>{row.supplier_name}</Td><Td>{row.destination}</Td><Td mono>{row.vessel_id}</Td><Td mono>{row.eta}</Td><Td>{row.status}</Td><Td align="right" mono>{row.delay_days.toFixed(1)}d</Td><Td mono>{row.source === "synthetic-demo" ? "demo-seeded" : row.source ?? "live"}</Td></tr>)}</tbody>
                    </table>
                  </div>
                ) : <EmptyState title="No shipment rows" copy="The shipments table is empty for this organization. AIS traffic above is the live logistics signal; shipment records arrive when procurement writes them." />}
              </div>
            </div>
          )}

          {section === "suppliers" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Supplier network" title={`${suppliers.length} registered suppliers`} />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse">
                  <thead className="bg-white/[.02]"><tr><Th>Supplier</Th><Th>Region</Th><Th align="right">Lead time</Th><Th align="right">MOQ</Th><Th align="right">Linked SKUs</Th><Th>Status</Th></tr></thead>
                  <tbody>{suppliers.map((row) => <tr key={row.id} className="border-t border-seam/70"><Td>{row.name}</Td><Td>{row.region}</Td><Td align="right" mono>{row.lead_time_days}d</Td><Td align="right" mono>{formatNumber(row.minimum_order_quantity)}</Td><Td align="right" mono>{row.active_products}</Td><Td>{row.active ? "active" : "inactive"}</Td></tr>)}</tbody>
                </table>
                {suppliers.length === 0 && <EmptyState title="No suppliers" copy="Register suppliers in Supabase to enable automated replenishment suggestions." />}
              </div>
            </div>
          )}

          {section === "purchase-orders" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Procurement" title={`${purchaseOrders.length} purchase orders`} />
              {purchaseOrders.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] border-collapse">
                    <thead className="bg-white/[.02]"><tr><Th>Order</Th><Th>Supplier</Th><Th>Warehouse</Th><Th>Status</Th><Th align="right">Amount</Th><Th>Created</Th></tr></thead>
                    <tbody>{purchaseOrders.map((row) => <tr key={row.id} className="border-t border-seam/70"><Td mono>{row.id.slice(0, 8)}</Td><Td>{row.supplier_name}</Td><Td>{row.warehouse_name}</Td><Td>{row.status}</Td><Td align="right" mono>{formatCurrency(row.total_amount)}</Td><Td mono>{formatDateTime(row.created_at)}</Td></tr>)}</tbody>
                  </table>
                </div>
              ) : <EmptyState title="No purchase orders yet" copy="Approve a recommendation in the queue and use “Create purchase order” to write a role-gated order with its line item." action={<button className="mt-3 rounded-sm bg-ice px-3 py-2 text-[11px] font-semibold text-shell hover:bg-white" onClick={() => goTo("ai-recommendations")}>Open approval queue</button>} />}
            </div>
          )}

          {section === "ai-recommendations" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Decision queue" title={`${recommendations.length} recommendations from the policy model`} />
              {recommendations.map((recommendation) => <RecommendationRow key={recommendation.id} recommendation={recommendation} onSelect={setSelectedRecommendation} onApprove={(id) => void handleApprove(id)} onReject={(id) => void handleReject(id)} />)}
              {recommendations.length === 0 && <EmptyState title="No actionable recommendations" copy="The policy model found no SKU inside the reorder envelope. Recommendations appear automatically when coverage drops below lead time." />}
            </div>
          )}

          {section === "risk" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Risk center" title="Warehouse × SKU risk scoring" />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse">
                  <thead className="bg-white/[.02]"><tr><Th>SKU</Th><Th>Warehouse</Th><Th align="right">Overall score</Th><Th align="right">Days cover</Th><Th>Level</Th><Th>Drivers</Th></tr></thead>
                  <tbody>{riskRows.map((row) => <tr key={`${row.warehouse_id}-${row.product_id}`} className="border-t border-seam/70"><Td mono>{row.sku}</Td><Td>{row.warehouse_name}</Td><Td align="right" mono>{row.overall_score.toFixed(2)}</Td><Td align="right" mono>{row.days_of_inventory.toFixed(1)}</Td><Td><RiskBadge risk={row.risk_level} /></Td><Td>{row.drivers.length > 0 ? row.drivers.join(", ").replaceAll("_", " ") : "—"}</Td></tr>)}</tbody>
                </table>
                {riskRows.length === 0 && <EmptyState title="No risk rows" copy="Risk scoring derives from inventory coverage and the policy model; no rows are visible yet." />}
              </div>
            </div>
          )}

          {section === "signals" && (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Agricultural rows" value={formatNumber(signals?.summary.agricultural_observations ?? 0)} detail="FAOSTAT food balance + production observations" tone="mint" icon={Leaf} />
                <MetricCard label="Crop indices" value={formatNumber(signals?.summary.crop_indices ?? 0)} detail="Sentinel-2 NDVI observations per AOI" tone="ice" icon={Satellite} />
                <MetricCard label="Food catalog" value={formatNumber(Object.values(signals?.summary.food_catalog_by_source ?? {}).reduce((sum, value) => sum + value, 0))} detail="Open Food Facts + USDA FoodData Central products" tone="orange" icon={Database} />
                <MetricCard label="Vessels" value={formatNumber(signals?.summary.vessels ?? 0)} detail="AIS vessel records with live positions" tone="coral" icon={ShipWheel} />
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="panel overflow-hidden rounded-sm">
                  <PanelHeader eyebrow="Sentinel-2" title="Crop health by area of interest" />
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] border-collapse">
                      <thead className="bg-white/[.02]"><tr><Th>AOI</Th><Th>Crop</Th><Th align="right">NDVI</Th><Th align="right">P10 / P90</Th><Th align="right">Health</Th><Th>Date</Th></tr></thead>
                      <tbody>{(signals?.crop_health ?? []).map((row: CropIndex) => <tr key={`${row.scene_id}-${row.aoi_name}`} className="border-t border-seam/70"><Td>{row.aoi_name}</Td><Td>{row.crop ?? "—"}</Td><Td align="right" mono>{row.ndvi_mean.toFixed(3)}</Td><Td align="right" mono>{row.ndvi_p10.toFixed(2)} / {row.ndvi_p90.toFixed(2)}</Td><Td align="right" mono>{Math.round(row.health_score * 100)}%</Td><Td mono>{row.observation_date}</Td></tr>)}</tbody>
                    </table>
                    {(signals?.crop_health ?? []).length === 0 && <EmptyState title="No NDVI observations" copy="Run the sentinel2 connector to compute crop-health indices for the configured AOIs." />}
                  </div>
                </div>
                <div className="panel overflow-hidden rounded-sm">
                  <PanelHeader eyebrow="FAOSTAT" title="Supply observations" />
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] border-collapse">
                      <thead className="bg-white/[.02]"><tr><Th>Region</Th><Th>Item</Th><Th>Element</Th><Th align="right">Value</Th><Th>Year</Th></tr></thead>
                      <tbody>{(signals?.agricultural ?? []).map((row, index) => <tr key={`${row.region}-${row.item}-${row.element}-${row.year}-${index}`} className="border-t border-seam/70"><Td>{row.region}</Td><Td>{row.item}</Td><Td>{row.element}</Td><Td align="right" mono>{formatNumber(row.value)} {row.unit ?? ""}</Td><Td mono>{row.year}</Td></tr>)}</tbody>
                    </table>
                    {(signals?.agricultural ?? []).length === 0 && <EmptyState title="No agricultural observations" copy="Run the faostat connector to load food balance and production rows." />}
                  </div>
                </div>
              </div>
              <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
                <div className="panel overflow-hidden rounded-sm">
                  <PanelHeader eyebrow="Food catalog" title="Reference products from Open Food Facts and USDA" />
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] border-collapse">
                      <thead className="bg-white/[.02]"><tr><Th>Name</Th><Th>Brand</Th><Th>Category</Th><Th>Nutri-Score</Th><Th>Allergens</Th><Th>Source</Th></tr></thead>
                      <tbody>{(signals?.food_catalog ?? []).map((row) => <tr key={`${row.source}-${row.source_id}`} className="border-t border-seam/70"><Td>{row.name}</Td><Td>{row.brand ?? "—"}</Td><Td>{row.category ?? row.data_type ?? "—"}</Td><Td mono>{row.nutriscore_grade ?? "—"}</Td><Td>{row.allergens.length > 0 ? row.allergens.slice(0, 3).join(", ") : "—"}</Td><Td mono>{row.source === "open_food_facts" ? "OFF" : "USDA"}</Td></tr>)}</tbody>
                    </table>
                    {(signals?.food_catalog ?? []).length === 0 && <EmptyState title="No catalog products" copy="Run the openfoodfacts or usda connectors to populate the food catalog." />}
                  </div>
                </div>
                <div className="panel overflow-hidden rounded-sm">
                  <PanelHeader eyebrow="Connectors" title="Recent ingestion runs" />
                  <div className="divide-y divide-seam/70">
                    {(signals?.summary.latest_runs ?? []).map((run, index) => (
                      <div key={`${run.provider}-${run.started_at}-${index}`} className="flex items-center justify-between px-4 py-3">
                        <div><div className="text-xs text-ink">{run.provider}</div><div className="mono text-[10px] text-muted">{run.dataset_code} · {formatDateTime(run.started_at)}</div></div>
                        <div className="text-right"><div className={`mono text-[11px] ${run.status === "succeeded" ? "text-mint" : "text-coral"}`}>{run.status}</div><div className="text-[10px] text-muted">{formatNumber(run.rows_written)} rows</div></div>
                      </div>
                    ))}
                    {(signals?.summary.latest_runs ?? []).length === 0 && <EmptyState title="No ingestion runs" copy="Run a connector from services/connectors to record its first run here." />}
                  </div>
                </div>
              </div>
            </div>
          )}

          {section === "simulation" && (
            <div className="panel rounded-sm">
              <PanelHeader eyebrow="Decision lab" title="Scenario simulator" />
              <div className="p-6">
                <p className="max-w-2xl text-sm leading-6 text-muted">The simulator compares the live baseline (inventory units, stockout exposure, pending orders, expected cost, service level) against a stressed scenario. It never mutates inventory or creates orders.</p>
                <button className="mt-4 inline-flex items-center gap-2 rounded-sm bg-ice px-4 py-2.5 text-xs font-semibold text-shell hover:bg-white" onClick={() => setSimulationOpen(true)}><Play size={13} />Open simulator</button>
                {simulation && (
                  <dl className="mt-6 grid gap-3 sm:grid-cols-3">
                    {Object.entries(simulation.scenario).map(([key, value]) => <div key={key} className="panel rounded-sm p-3"><dt className="eyebrow">{key.replaceAll("_", " ")}</dt><dd className="mono mt-2 text-lg text-ink">{typeof value === "number" ? value.toFixed(2) : String(value)}</dd></div>)}
                  </dl>
                )}
              </div>
            </div>
          )}

          {section === "audit-log" && (
            <div className="panel overflow-hidden rounded-sm">
              <PanelHeader eyebrow="Audit trail" title={`${auditEntries.length} recent entries`} />
              {auditEntries.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] border-collapse">
                    <thead className="bg-white/[.02]"><tr><Th>Action</Th><Th>Entity</Th><Th>Actor</Th><Th>Metadata</Th><Th>When</Th></tr></thead>
                    <tbody>{auditEntries.map((row) => <tr key={row.id} className="border-t border-seam/70"><Td mono>{row.action}</Td><Td>{row.entity_type ?? "—"}</Td><Td>{row.actor ?? "—"}</Td><Td mono>{JSON.stringify(row.metadata)}</Td><Td mono>{formatDateTime(row.created_at)}</Td></tr>)}</tbody>
                  </table>
                </div>
              ) : <EmptyState title="No audit entries yet" copy="Approving or rejecting a recommendation writes an audit row through the API under your session." />}
            </div>
          )}

          {section === "settings" && (
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="panel rounded-sm">
                <PanelHeader eyebrow="Runtime" title="API and repository status" />
                <div className="space-y-2 p-4 text-xs text-muted">
                  <div className="flex justify-between"><span>API URL</span><span className="mono text-ink">{process.env.NEXT_PUBLIC_API_URL ?? "unset"}</span></div>
                  <div className="flex justify-between"><span>Supabase URL</span><span className="mono text-ink">{process.env.NEXT_PUBLIC_SUPABASE_URL ?? "unset"}</span></div>
                  <div className="flex justify-between"><span>Signed-in operator</span><span className="mono text-ink">{email ?? "unknown"}</span></div>
                  <div className="flex justify-between"><span>Rows read this session</span><span className="mono text-ink">{inventory.length + recommendations.length + vessels.length + (signals?.summary.agricultural_observations ?? 0)}</span></div>
                </div>
              </div>
              <div className="panel rounded-sm">
                <PanelHeader eyebrow="Access model" title="How writes are protected" />
                <ul className="space-y-3 p-4 text-xs leading-6 text-muted">
                  <li>Reads run under your Supabase JWT, so row level security decides what this account can see.</li>
                  <li>Approvals and purchase orders call the API with that same token; roles are checked against <span className="mono text-ink">profiles.role</span>.</li>
                  <li>External reference data (FAOSTAT, Sentinel-2, AIS, food catalogs) is world-readable and written only by the connectors with the service role.</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {selectedRecommendation && <Drawer recommendation={selectedRecommendation} onClose={() => setSelectedRecommendation(null)} onApprove={(id) => void handleApprove(id)} onReject={(id) => void handleReject(id)} onCreateOrder={(id) => void handleCreateOrder(id)} busy={busy} />}
        {simulationOpen && <SimulationPanel onClose={() => setSimulationOpen(false)} onRun={(input) => void handleSimulation(input)} result={simulation} running={simulationRunning} error={null} />}
        {toast && <div className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-sm border border-mint/25 bg-[#0d211f] px-4 py-3 text-xs text-mint shadow-glow"><Check size={14} />{toast}</div>}
      </main>
    </div>
  );
}
