"use client";

import { useEffect, useState } from "react";
import { Unavailable } from "@/components/Block";
import { useSolanaWallet } from "@/components/SolanaWallet";
import { toSmallestUnit, fromSmallestUnit } from "@/lib/solanaWallet";
import {
  fetchJupiterConfig,
  fetchSwapHistory,
  fetchSwapQuote,
  fetchUsdcMint,
  fetchXStocks,
  recordSwapFill,
  signAndSendSwap,
  type JupiterConfig,
  type SwapFillOut,
  type SwapQuote,
  type XStock,
} from "@/lib/jupiter";
import styles from "./TradingView.module.css";

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function XStocksView() {
  const wallet = useSolanaWallet();
  const [config, setConfig] = useState<JupiterConfig | null | undefined>(undefined);
  const [xstocks, setXStocks] = useState<XStock[] | null | undefined>(undefined);
  const [usdcMint, setUsdcMint] = useState<string | null>(null);
  const [history, setHistory] = useState<SwapFillOut[]>([]);

  const [selected, setSelected] = useState<string>("");
  const [amount, setAmount] = useState("10");
  const [quote, setQuote] = useState<SwapQuote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [swapping, setSwapping] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  useEffect(() => {
    fetchJupiterConfig().then(setConfig);
    fetchXStocks().then(setXStocks);
    fetchUsdcMint().then((r) => setUsdcMint(r?.mint ?? null));
  }, []);

  useEffect(() => {
    if (!wallet.address) {
      setHistory([]);
      return;
    }
    fetchSwapHistory(wallet.address).then((fills) => setHistory(fills ?? []));
  }, [wallet.address, lastResult]);

  useEffect(() => {
    if (!wallet.address) wallet.refreshWallets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallet.address]);

  useEffect(() => {
    if (xstocks && xstocks.length > 0 && !selected) setSelected(xstocks[0].symbol);
  }, [xstocks, selected]);

  const selectedStock = xstocks?.find((x) => x.symbol === selected) ?? null;

  async function handleGetQuote() {
    if (!usdcMint || !selectedStock) return;
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setActionError("Enter a USDC amount greater than zero.");
      return;
    }
    setQuoting(true);
    setActionError(null);
    setQuote(null);
    try {
      const result = await fetchSwapQuote({
        inputMint: usdcMint,
        outputMint: selectedStock.mint,
        amount: toSmallestUnit(amount, 6),
      });
      if (!result) throw new Error("No route found for that swap right now.");
      setQuote(result);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not get a quote.");
    } finally {
      setQuoting(false);
    }
  }

  async function handleSwap() {
    if (!wallet.provider || !wallet.address || !quote || !selectedStock) {
      setActionError("Wallet isn't fully connected yet — reconnect and try again.");
      return;
    }
    setSwapping(true);
    setActionError(null);
    setLastResult(null);
    try {
      const signature = await signAndSendSwap(wallet.provider, wallet.address, quote.raw_quote);
      await recordSwapFill({
        walletAddress: wallet.address,
        inputMint: quote.input_mint,
        outputMint: quote.output_mint,
        inAmount: quote.in_amount,
        outAmount: quote.out_amount,
        signature,
      });
      setLastResult(`Swapped for ${fromSmallestUnit(quote.out_amount, selectedStock.decimals)} ${selectedStock.symbol} — ${signature.slice(0, 12)}…`);
      setQuote(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Swap failed.");
    } finally {
      setSwapping(false);
    }
  }

  if (config === undefined || xstocks === undefined) return null;

  if (!xstocks) {
    return <Unavailable reason="No xStocks reachable right now." />;
  }

  const publicEquities = xstocks.filter((x) => x.category === "public_equity");
  const preIpo = xstocks.filter((x) => x.category === "pre_ipo");

  return (
    <div className={styles.stack}>
      <div className={styles.banner}>
        {config?.trading_enabled
          ? "MAINNET — real funds. Unregulated on-chain tokenized equities via Jupiter (jup.ag). Price-exposure only, no shareholder rights. Legal status varies by jurisdiction. Not investment advice."
          : "Read-only — live signing isn't enabled on this deployment yet. Prices below are real; swapping is disabled."}
      </div>

      <div className={styles.section}>
        <h3>Public-equity xStocks</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Price (USD)</th>
            </tr>
          </thead>
          <tbody>
            {publicEquities.map((x) => (
              <tr key={x.symbol}>
                <td>{x.symbol}</td>
                <td>{x.name}</td>
                <td>${x.price_usd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {preIpo.length > 0 && (
        <div className={styles.section}>
          <h3>Pre-IPO / private exposure</h3>
          <p className={styles.address}>
            Synthetic trackers or fund wrappers — not a direct share, no shareholder rights.
          </p>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Name</th>
                <th>Price (USD)</th>
              </tr>
            </thead>
            <tbody>
              {preIpo.map((x) => (
                <tr key={x.symbol}>
                  <td>{x.symbol}</td>
                  <td>{x.name}</td>
                  <td>${x.price_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {config?.trading_enabled && (
        <div className={styles.section}>
          {wallet.address ? (
            <div className={styles.row}>
              <span className={styles.address}>{wallet.address}</span>
              <button className={styles.buttonSecondary} onClick={wallet.disconnect} type="button">
                Disconnect
              </button>
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
              No Solana wallet extension found — install Phantom or Solflare to swap.
            </span>
          )}
          {wallet.error && <span className={styles.error}>{wallet.error}</span>}
          {actionError && <span className={styles.error}>{actionError}</span>}
          {lastResult && <span className={styles.result}>{lastResult}</span>}
        </div>
      )}

      {config?.trading_enabled && wallet.address && (
        <div className={styles.section}>
          <div className={styles.form}>
            <label className={styles.field}>
              xStock
              <select value={selected} onChange={(e) => { setSelected(e.target.value); setQuote(null); }}>
                {xstocks.map((x) => (
                  <option key={x.symbol} value={x.symbol}>
                    {x.symbol}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              USDC amount
              <input
                type="number"
                step="any"
                min="0"
                value={amount}
                onChange={(e) => { setAmount(e.target.value); setQuote(null); }}
              />
            </label>
            <button className={styles.button} type="button" onClick={handleGetQuote} disabled={quoting}>
              {quoting ? "Quoting…" : "Get quote"}
            </button>
          </div>
          {quote && selectedStock && (
            <div className={styles.row}>
              <span className={styles.result}>
                ≈ {fromSmallestUnit(quote.out_amount, selectedStock.decimals)} {selectedStock.symbol}{" "}
                (price impact {quote.price_impact_pct.toFixed(2)}%)
              </span>
              <button className={styles.button} type="button" onClick={handleSwap} disabled={swapping}>
                {swapping ? "Submitting…" : "Confirm swap"}
              </button>
            </div>
          )}
        </div>
      )}

      {wallet.address && history.length > 0 && (
        <div className={styles.section}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>In</th>
                <th>Out</th>
                <th>Signature</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {history.map((fill) => (
                <tr key={fill.id}>
                  <td>{fill.in_amount}</td>
                  <td>{fill.out_amount}</td>
                  <td>{fill.signature.slice(0, 10)}…</td>
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
