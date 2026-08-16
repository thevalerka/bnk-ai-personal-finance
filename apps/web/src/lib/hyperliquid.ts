// Client-side Hyperliquid signing + submission (docs/DECISIONS.md
// ADR-0028). Everything here runs in the visitor's own browser against the
// wallet they just connected — the backend never sees an order or approval
// before it's signed, and never signs anything itself. Uses
// `@nktkas/hyperliquid` rather than hand-rolling the msgpack+EIP-712
// "Agent" signing scheme Hyperliquid's L1 actions require (documented in
// the ADR, and the exact reason a battle-tested SDK was chosen over a
// hand-rolled signer for a financial action).

import { ExchangeClient, HttpTransport, InfoClient } from "@nktkas/hyperliquid";
import type { AbstractWallet } from "@nktkas/hyperliquid/signing";
import { formatPrice, formatSize, SymbolConverter } from "@nktkas/hyperliquid/utils";
import type { WalletClient } from "viem";

// viem's WalletClient type requires `account` on every signTypedData call
// site structurally, even though at runtime it falls back to the account
// bound at client creation (lib/wallet.ts always binds one) when omitted —
// a known friction point between the two libraries' type signatures, not a
// runtime gap. The SDK's AbstractWallet interface is exactly the duck-typed
// surface (signTypedData/getAddresses/getChainId) a bound WalletClient
// already satisfies at runtime.
function asAbstractWallet(client: WalletClient): AbstractWallet {
  return client as unknown as AbstractWallet;
}

// Testnet only — this feature has no mainnet/live-funds path yet
// (docs/PLAN.md section 6's opt-in-behind-a-flag requirement for that).
const transport = new HttpTransport({ isTestnet: true });
const info = new InfoClient({ transport });

let converterPromise: Promise<SymbolConverter> | null = null;
function getConverter(): Promise<SymbolConverter> {
  converterPromise ??= SymbolConverter.create({ transport });
  return converterPromise;
}

export async function fetchMidPrice(coin: string): Promise<number | null> {
  const mids = await info.allMids();
  const mid = mids[coin];
  return mid ? Number(mid) : null;
}

export async function approveBuilderFeeOnChain(
  wallet: WalletClient,
  builderAddress: string,
  builderFeeTenthsBp: number,
): Promise<void> {
  const exchange = new ExchangeClient({ transport, wallet: asAbstractWallet(wallet) });
  // Hyperliquid wants a percentage string ("0.01%"); tenths-of-a-bp (our
  // and the backend's shared unit, 10 = 1bp) divided by 1000 gives percent.
  const maxFeeRate = `${(builderFeeTenthsBp / 1000).toFixed(3)}%`;
  await exchange.approveBuilderFee({ builder: builderAddress as `0x${string}`, maxFeeRate });
}

export interface OrderParams {
  coin: string; // Hyperliquid perp coin name, e.g. "BTC"
  isBuy: boolean;
  size: number;
  price: number;
  tif: "Gtc" | "Ioc" | "Alo";
}

export interface OrderOutcome {
  orderId: number;
  resting: boolean;
}

export async function placeOrder(
  wallet: WalletClient,
  builderAddress: string,
  builderFeeTenthsBp: number,
  params: OrderParams,
): Promise<OrderOutcome> {
  const converter = await getConverter();
  const assetId = converter.getAssetId(params.coin);
  if (assetId === undefined) {
    throw new Error(`Unknown Hyperliquid asset: ${params.coin}`);
  }
  const szDecimals = converter.getSzDecimals(params.coin) ?? 0;

  const exchange = new ExchangeClient({ transport, wallet: asAbstractWallet(wallet) });
  const result = await exchange.order({
    orders: [
      {
        a: assetId,
        b: params.isBuy,
        p: formatPrice(params.price, szDecimals),
        s: formatSize(params.size, szDecimals),
        r: false,
        t: { limit: { tif: params.tif } },
      },
    ],
    grouping: "na",
    builder: { b: builderAddress as `0x${string}`, f: builderFeeTenthsBp },
  });

  const status = result.response.data.statuses[0];
  if (status === "waitingForFill" || status === "waitingForTrigger") {
    throw new Error(`Order not yet resolved: ${status}`);
  }
  if ("error" in status) {
    throw new Error(String(status.error));
  }
  if ("filled" in status) {
    return { orderId: status.filled.oid, resting: false };
  }
  return { orderId: status.resting.oid, resting: true };
}
