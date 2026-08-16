// Client-side (browser) fetch layer for apps/api's `/trading/*` — same
// NEXT_PUBLIC_API_PUBLIC_URL + credentials convention as lib/attention.ts
// and lib/agent.ts. Every call here happens *after* the browser has
// already signed and (for orders) submitted directly to Hyperliquid
// (lib/hyperliquid.ts) — these endpoints only log confirmed activity for
// commission accounting, they never build or relay a signable action.

const API_PUBLIC_URL = process.env.NEXT_PUBLIC_API_PUBLIC_URL ?? "http://localhost:8100";

export interface TradingConfig {
  builder_address: string;
  builder_fee_tenths_bp: number;
  testnet_base_url: string;
  configured: boolean;
}

export interface FillOut {
  id: number;
  wallet_address: string;
  coin: string;
  side: "buy" | "sell";
  size: number;
  price: number;
  builder_fee_tenths_bp: number;
  created_at: string;
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

async function postJSON<T>(path: string, body: unknown): Promise<T | null> {
  try {
    const response = await fetch(`${API_PUBLIC_URL}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function fetchTradingConfig(): Promise<TradingConfig | null> {
  return getJSON<TradingConfig>("/trading/config");
}

export function recordApproval(
  walletAddress: string,
  maxFeeTenthsBp: number,
): Promise<unknown | null> {
  return postJSON("/trading/approvals", {
    wallet_address: walletAddress,
    max_fee_tenths_bp: maxFeeTenthsBp,
  });
}

export function recordFill(params: {
  walletAddress: string;
  coin: string;
  side: "buy" | "sell";
  size: number;
  price: number;
  orderId: number;
}): Promise<FillOut | null> {
  return postJSON<FillOut>("/trading/fills", {
    wallet_address: params.walletAddress,
    coin: params.coin,
    side: params.side,
    size: params.size,
    price: params.price,
    order_id: params.orderId,
  });
}

export function fetchOrderHistory(walletAddress: string): Promise<FillOut[] | null> {
  return getJSON<FillOut[]>(`/trading/orders?wallet=${encodeURIComponent(walletAddress)}`);
}
