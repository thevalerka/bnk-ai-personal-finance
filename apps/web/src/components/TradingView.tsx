"use client";

import { useEffect, useState } from "react";
import { Unavailable } from "@/components/Block";
import { useWallet } from "@/components/Wallet";
import { approveBuilderFeeOnChain, fetchMidPrice, placeOrder } from "@/lib/hyperliquid";
import {
  fetchOrderHistory,
  fetchTradingConfig,
  recordApproval,
  recordFill,
  type FillOut,
  type TradingConfig,
} from "@/lib/trading";
import styles from "./TradingView.module.css";

// Small curated list matching the coins the existing read-only
// `hyperliquid.py` info provider already quotes — keeps the dropdown to
// real, known-liquid testnet perps rather than every listed asset.
const COINS = ["BTC", "ETH", "SOL"];

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function TradingView() {
  const wallet = useWallet();
  const [config, setConfig] = useState<TradingConfig | null | undefined>(undefined);
  const [history, setHistory] = useState<FillOut[]>([]);

  const [coin, setCoin] = useState(COINS[0]);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [size, setSize] = useState("0.01");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");

  const [approving, setApproving] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  useEffect(() => {
    fetchTradingConfig().then(setConfig);
  }, []);

  useEffect(() => {
    if (!wallet.address) {
      setHistory([]);
      return;
    }
    fetchOrderHistory(wallet.address).then((fills) => setHistory(fills ?? []));
  }, [wallet.address, lastResult]);

  useEffect(() => {
    if (!wallet.address) wallet.refreshWallets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallet.address]);

  async function handleApprove() {
    if (!wallet.client || !wallet.address || !config) return;
    setApproving(true);
    setActionError(null);
    try {
      await approveBuilderFeeOnChain(wallet.client, config.builder_address, config.builder_fee_tenths_bp);
      await recordApproval(wallet.address, config.builder_fee_tenths_bp);
      wallet.markBuilderApproved();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Builder-fee approval failed.");
    } finally {
      setApproving(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!wallet.client || !wallet.address || !config) return;
    const parsedSize = Number(size);
    if (!Number.isFinite(parsedSize) || parsedSize <= 0) {
      setActionError("Enter a size greater than zero.");
      return;
    }

    setPlacing(true);
    setActionError(null);
    setLastResult(null);
    try {
      let price: number;
      let tif: "Gtc" | "Ioc";
      if (orderType === "market") {
        const mid = await fetchMidPrice(coin);
        if (mid === null) throw new Error(`No live price for ${coin}.`);
        // Market order = an aggressive IOC limit through the book, with a
        // 1% slippage tolerance — Hyperliquid has no separate "market"
        // order type (docs/DECISIONS.md ADR-0028).
        price = side === "buy" ? mid * 1.01 : mid * 0.99;
        tif = "Ioc";
      } else {
        const parsedPrice = Number(limitPrice);
        if (!Number.isFinite(parsedPrice) || parsedPrice <= 0) {
          throw new Error("Enter a limit price greater than zero.");
        }
        price = parsedPrice;
        tif = "Gtc";
      }

      const outcome = await placeOrder(wallet.client, config.builder_address, config.builder_fee_tenths_bp, {
        coin,
        isBuy: side === "buy",
        size: parsedSize,
        price,
        tif,
      });
      await recordFill({
        walletAddress: wallet.address,
        coin,
        side,
        size: parsedSize,
        price,
        orderId: outcome.orderId,
      });
      setLastResult(
        outcome.resting
          ? `Order #${outcome.orderId} placed, resting on the book.`
          : `Order #${outcome.orderId} filled.`,
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Order failed.");
    } finally {
      setPlacing(false);
    }
  }

  if (config === undefined) return null;

  if (!config?.configured) {
    return (
      <Unavailable reason="Trading isn't configured yet — no builder address is set (docs/DECISIONS.md ADR-0028)." />
    );
  }

  return (
    <div className={styles.stack}>
      <div className={styles.banner}>TESTNET — no real funds. Hyperliquid testnet only.</div>

      <div className={styles.section}>
        {wallet.address ? (
          <div className={styles.row}>
            <span className={styles.address}>{wallet.address}</span>
            <button className={styles.buttonSecondary} onClick={wallet.disconnect} type="button">
              Disconnect
            </button>
            {!wallet.builderApproved && (
              <button className={styles.button} onClick={handleApprove} disabled={approving} type="button">
                {approving ? "Approving…" : "Approve builder fee (testnet)"}
              </button>
            )}
            {wallet.builderApproved && <span className={styles.result}>Builder fee approved ✓</span>}
          </div>
        ) : wallet.availableWallets.length > 0 ? (
          <div className={styles.row}>
            {wallet.availableWallets.map((option) => (
              <button
                key={option.id}
                className={styles.button}
                onClick={() => wallet.connect(option.id)}
                disabled={wallet.connecting}
                type="button"
              >
                {wallet.connecting ? "Connecting…" : `Connect ${option.name}`}
              </button>
            ))}
          </div>
        ) : (
          <span className={styles.address}>
            No wallet extension found — install MetaMask or Phantom to trade.
          </span>
        )}
        {wallet.error && <span className={styles.error}>{wallet.error}</span>}
      </div>

      {wallet.address && wallet.builderApproved && (
        <form className={styles.section} onSubmit={handleSubmit}>
          <div className={styles.form}>
            <label className={styles.field}>
              Coin
              <select value={coin} onChange={(e) => setCoin(e.target.value)}>
                {COINS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Side
              <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>
            <label className={styles.field}>
              Size
              <input
                type="number"
                step="any"
                min="0"
                value={size}
                onChange={(e) => setSize(e.target.value)}
              />
            </label>
            <label className={styles.field}>
              Order type
              <select value={orderType} onChange={(e) => setOrderType(e.target.value as "market" | "limit")}>
                <option value="market">Market</option>
                <option value="limit">Limit</option>
              </select>
            </label>
            {orderType === "limit" && (
              <label className={styles.field}>
                Limit price
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={limitPrice}
                  onChange={(e) => setLimitPrice(e.target.value)}
                />
              </label>
            )}
            <button className={styles.button} type="submit" disabled={placing}>
              {placing ? "Submitting…" : "Place order"}
            </button>
          </div>
          {actionError && <span className={styles.error}>{actionError}</span>}
          {lastResult && <span className={styles.result}>{lastResult}</span>}
        </form>
      )}

      {wallet.address && history.length > 0 && (
        <div className={styles.section}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Coin</th>
                <th>Side</th>
                <th>Size</th>
                <th>Price</th>
                <th>Builder fee</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {history.map((fill) => (
                <tr key={fill.id}>
                  <td>{fill.coin}</td>
                  <td>{fill.side}</td>
                  <td>{fill.size}</td>
                  <td>{fill.price}</td>
                  <td>{(fill.builder_fee_tenths_bp / 10).toFixed(1)}bp</td>
                  <td>{relativeTime(fill.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
