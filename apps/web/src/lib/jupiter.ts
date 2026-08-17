// Client-side (browser) fetch layer for apps/api's `/jupiter/*` — same
// NEXT_PUBLIC_API_PUBLIC_URL + credentials convention as lib/trading.ts.
// Unlike lib/hyperliquid.ts, the *quote* and *unsigned transaction* itself
// come from this backend (a proxy in front of Jupiter, since Jupiter's API
// needs a secret x-api-key the browser can't safely hold) — only the
// signing step happens client-side, via signAndSendJupiterTransaction
// below (docs/DECISIONS.md ADR-0029).

import { VersionedTransaction } from "@solana/web3.js";
import type { SolanaProvider } from "./solanaWallet";

const API_PUBLIC_URL = process.env.NEXT_PUBLIC_API_PUBLIC_URL ?? "http://localhost:8100";

export interface JupiterConfig {
  trading_enabled: boolean;
  platform_fee_bps: number;
  configured: boolean;
}

export interface XStock {
  symbol: string;
  name: string;
  mint: string;
  decimals: number;
  price_usd: number;
  category: "public_equity" | "pre_ipo";
  note: string;
}

export interface LendToken {
  asset_mint: string;
  symbol: string;
  decimals: number;
  supply_apy_pct: number;
  total_supplied_usd: number;
}

export interface SwapQuote {
  input_mint: string;
  output_mint: string;
  in_amount: string;
  out_amount: string;
  price_impact_pct: number;
  raw_quote: Record<string, unknown>;
}

export interface SwapFillOut {
  id: number;
  wallet_address: string;
  input_mint: string;
  output_mint: string;
  in_amount: string;
  out_amount: string;
  signature: string;
  platform_fee_bps: number;
  created_at: string;
}

export interface LendFillOut {
  id: number;
  wallet_address: string;
  asset_mint: string;
  action: "deposit" | "withdraw";
  amount: string;
  signature: string;
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

export function fetchJupiterConfig(): Promise<JupiterConfig | null> {
  return getJSON<JupiterConfig>("/jupiter/config");
}

export function fetchXStocks(): Promise<XStock[] | null> {
  return getJSON<XStock[]>("/jupiter/xstocks");
}

export function fetchLendTokens(): Promise<LendToken[] | null> {
  return getJSON<LendToken[]>("/jupiter/lend-tokens");
}

export function fetchUsdcMint(): Promise<{ mint: string } | null> {
  return getJSON<{ mint: string }>("/jupiter/usdc-mint");
}

export function fetchSwapQuote(params: {
  inputMint: string;
  outputMint: string;
  amount: string;
  slippageBps?: number;
}): Promise<SwapQuote | null> {
  return postJSON<SwapQuote>("/jupiter/swap-quote", {
    input_mint: params.inputMint,
    output_mint: params.outputMint,
    amount: params.amount,
    slippage_bps: params.slippageBps ?? 50,
  });
}

function fetchSwapTransaction(
  walletAddress: string,
  quote: Record<string, unknown>,
): Promise<{ transaction: string } | null> {
  return postJSON("/jupiter/swap-transaction", { wallet_address: walletAddress, quote });
}

function fetchLendTransaction(params: {
  walletAddress: string;
  assetMint: string;
  action: "deposit" | "withdraw";
  amount: string;
}): Promise<{ transaction: string } | null> {
  return postJSON("/jupiter/lend-transaction", {
    wallet_address: params.walletAddress,
    asset_mint: params.assetMint,
    action: params.action,
    amount: params.amount,
  });
}

export function recordSwapFill(params: {
  walletAddress: string;
  inputMint: string;
  outputMint: string;
  inAmount: string;
  outAmount: string;
  signature: string;
}): Promise<SwapFillOut | null> {
  return postJSON<SwapFillOut>("/jupiter/swap-fills", {
    wallet_address: params.walletAddress,
    input_mint: params.inputMint,
    output_mint: params.outputMint,
    in_amount: params.inAmount,
    out_amount: params.outAmount,
    signature: params.signature,
  });
}

export function recordLendFill(params: {
  walletAddress: string;
  assetMint: string;
  action: "deposit" | "withdraw";
  amount: string;
  signature: string;
}): Promise<LendFillOut | null> {
  return postJSON<LendFillOut>("/jupiter/lend-fills", {
    wallet_address: params.walletAddress,
    asset_mint: params.assetMint,
    action: params.action,
    amount: params.amount,
    signature: params.signature,
  });
}

export function fetchSwapHistory(walletAddress: string): Promise<SwapFillOut[] | null> {
  return getJSON<SwapFillOut[]>(`/jupiter/swap-history?wallet=${encodeURIComponent(walletAddress)}`);
}

export function fetchLendHistory(walletAddress: string): Promise<LendFillOut[] | null> {
  return getJSON<LendFillOut[]>(`/jupiter/lend-history?wallet=${encodeURIComponent(walletAddress)}`);
}

/** Asks this backend to build the unsigned transaction, deserializes it,
 * and hands it to the wallet to sign + submit directly to Solana — the
 * backend never sees a signature (CLAUDE.md: client-side signing only). */
export async function signAndSendSwap(
  provider: SolanaProvider,
  walletAddress: string,
  quote: Record<string, unknown>,
): Promise<string> {
  const built = await fetchSwapTransaction(walletAddress, quote);
  if (!built) throw new Error("Could not build the swap transaction.");
  const tx = VersionedTransaction.deserialize(Buffer.from(built.transaction, "base64"));
  const { signature } = await provider.signAndSendTransaction(tx);
  return signature;
}

export async function signAndSendLend(
  provider: SolanaProvider,
  params: { walletAddress: string; assetMint: string; action: "deposit" | "withdraw"; amount: string },
): Promise<string> {
  const built = await fetchLendTransaction(params);
  if (!built) throw new Error("Could not build the lend transaction.");
  const tx = VersionedTransaction.deserialize(Buffer.from(built.transaction, "base64"));
  const { signature } = await provider.signAndSendTransaction(tx);
  return signature;
}
