// Client-side (browser) fetch layer for the attention engine (apps/api
// `/profile/*`), used from Client Components only — unlike lib/market.ts,
// which fetches server-side from Server Components. NEXT_PUBLIC_API_BASE_URL
// (lib/market.ts) is a same-box loopback address in production, unreachable
// from a visitor's own browser; NEXT_PUBLIC_API_PUBLIC_URL is the real
// public API origin, and every call here sends credentials so the
// amt_profile cookie (docs/PLAN.md section 4.1) round-trips correctly
// across the web/api subdomains.

const API_PUBLIC_URL = process.env.NEXT_PUBLIC_API_PUBLIC_URL ?? "http://localhost:8100";

export type EventKind =
  | "impression"
  | "dwell"
  | "hover"
  | "click"
  | "chart_interaction"
  | "search"
  | "agent_mention"
  | "pin"
  | "mute";

export interface EventIn {
  node_id: string;
  kind: EventKind;
  magnitude?: number;
  meta?: Record<string, unknown>;
}

export interface BlockPlan {
  block_type: string;
  nodes: string[];
  raw_score: number;
  area_weight: number;
  columns: number;
  priority: number;
}

export interface LayoutPlan {
  blocks: BlockPlan[];
}

export interface SourceEvent {
  kind: string;
  weight: number;
  ts: string;
  node_id: string;
  meta: Record<string, unknown> | null;
}

export interface ExplainResult {
  node_id: string;
  score: number;
  last_updated: string | null;
  muted: boolean;
  source_events: SourceEvent[];
}

export interface PersonaOut {
  name: string;
  label: string;
  description: string;
}

export interface ProfileOut {
  profile_id: string;
  persona: string | null;
  layout: LayoutPlan;
}

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_PUBLIC_URL}${path}`, { credentials: "include" });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function postJSON<T>(path: string, body?: unknown): Promise<T | null> {
  try {
    const response = await fetch(`${API_PUBLIC_URL}${path}`, {
      method: "POST",
      credentials: "include",
      // fetch + keepalive rather than navigator.sendBeacon: sendBeacon
      // can't reliably do a JSON content-type + credentialed CORS request
      // (it's speced around simple/no-cors requests) across the
      // web/api subdomain split this app uses in production. keepalive
      // gives the same "survives page unload" guarantee for the small
      // batches this sends.
      keepalive: true,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) return null;
    if (response.status === 204) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function postEvents(events: EventIn[]): Promise<void | null> {
  if (events.length === 0) return Promise.resolve(null);
  return postJSON<void>("/profile/events", { events });
}

export function fetchVector(): Promise<Record<string, number> | null> {
  return getJSON<Record<string, number>>("/profile/vector");
}

export function fetchLayout(): Promise<LayoutPlan | null> {
  return getJSON<LayoutPlan>("/profile/layout");
}

export function fetchExplain(nodeId: string): Promise<ExplainResult | null> {
  return getJSON<ExplainResult>(`/profile/explain?node_id=${encodeURIComponent(nodeId)}`);
}

export function fetchPersonas(): Promise<PersonaOut[] | null> {
  return getJSON<PersonaOut[]>("/profile/personas");
}

export function fetchMe(): Promise<ProfileOut | null> {
  return getJSON<ProfileOut>("/profile/me");
}

export function viewAsPersona(name: string): Promise<ProfileOut | null> {
  return postJSON<ProfileOut>(`/profile/persona/${encodeURIComponent(name)}`);
}

export function resetProfile(): Promise<ProfileOut | null> {
  return postJSON<ProfileOut>("/profile/reset");
}
