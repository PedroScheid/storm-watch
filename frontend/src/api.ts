// Cliente da API do StormWatch.

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Intensity = "moderada" | "forte" | "muito_forte";

export interface MonitorPayload {
  lat: number;
  lon: number;
  min_intensity: Intensity;
  alert_radius_km: number;
  subscription: PushSubscriptionJSON;
}

export interface Cell {
  intensity: Intensity;
  eta_minutes: number | null;
  distance_km: number;
  bearing_deg: number;
  speed_kmh: number;
  approaching: boolean;
}

export interface Nowcast {
  lat: number;
  lon: number;
  generated_at: number;
  frame_time: string | null;
  cells: Cell[];
}

export async function getVapidPublicKey(): Promise<string> {
  const r = await fetch(`${BASE}/vapid-public-key`);
  if (!r.ok) throw new Error("Falha ao obter chave VAPID");
  return (await r.json()).public_key;
}

export async function createMonitor(payload: MonitorPayload): Promise<void> {
  const r = await fetch(`${BASE}/monitors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Falha ao registrar monitoramento");
}

export async function unsubscribe(endpoint: string): Promise<void> {
  await fetch(`${BASE}/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint }),
  });
}

export async function getNowcast(
  lat: number,
  lon: number,
  minIntensity: Intensity,
  radiusKm: number
): Promise<Nowcast> {
  const q = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    min_intensity: minIntensity,
    alert_radius_km: String(radiusKm),
  });
  const r = await fetch(`${BASE}/nowcast?${q}`);
  if (!r.ok) throw new Error("Falha ao consultar nowcast");
  return r.json();
}
