"use client";

import { useEffect, useState } from "react";
import { Unavailable } from "@/components/Block";
import { useSolanaWallet } from "@/components/SolanaWallet";
import { toSmallestUnit } from "@/lib/solanaWallet";
import {
  fetchJupiterConfig,
  fetchLendHistory,
  fetchLendTokens,
  recordLendFill,
  signAndSendLend,
  type JupiterConfig,
  type LendFillOut,
  type LendToken,
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

export function LendView() {
  const wallet = useSolanaWallet();
  const [config, setConfig] = useState<JupiterConfig | null | undefined>(undefined);
  const [tokens, setTokens] = useState<LendToken[] | null | undefined>(undefined);
  const [history, setHistory] = useState<LendFillOut[]>([]);

  const [selected, setSelected] = useState<string>("");
  const [action, setAction] = useState<"deposit" | "withdraw">("deposit");
  const [amount, setAmount] = useState("100");
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  useEffect(() => {
    fetchJupiterConfig().then(setConfig);
    fetchLendTokens().then(setTokens);
  }, []);

  useEffect(() => {
    if (!wallet.address) {
      setHistory([]);
      return;
    }
    fetchLendHistory(wallet.address).then((fills) => setHistory(fills ?? []));
  }, [wallet.address, lastResult]);

  useEffect(() => {
    if (!wallet.address) wallet.refreshWallets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallet.address]);

  useEffect(() => {
    if (tokens && tokens.length > 0 && !selected) setSelected(tokens[0].asset_mint);
  }, [tokens, selected]);

  const selectedToken = tokens?.find((t) => t.asset_mint === selected) ?? null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!wallet.provider || !wallet.address || !selectedToken) {
      setActionError("Wallet isn't fully connected yet — reconnect and try again.");
      return;
    }
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setActionError("Enter an amount greater than zero.");
      return;
    }

    setSubmitting(true);
    setActionError(null);
    setLastResult(null);
    try {
      const smallestUnit = toSmallestUnit(amount, selectedToken.decimals);
      const signature = await signAndSendLend(wallet.provider, {
        walletAddress: wallet.address,
        assetMint: selectedToken.asset_mint,
        action,
        amount: smallestUnit,
      });
      await recordLendFill({
        walletAddress: wallet.address,
        assetMint: selectedToken.asset_mint,
        action,
        amount: smallestUnit,
        signature,
      });
      setLastResult(
        `${action === "deposit" ? "Deposited" : "Withdrew"} ${amount} ${selectedToken.symbol} — ${signature.slice(0, 12)}…`,
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Transaction failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (config === undefined || tokens === undefined) return null;

  if (!tokens) {
    return <Unavailable reason="No stablecoin lend vaults reachable right now." />;
  }

  return (
    <div className={styles.stack}>
      <div className={styles.banner}>
        {config?.trading_enabled
          ? "MAINNET — real funds. Unregulated on-chain stablecoin lending via Jupiter Lend (jup.ag). Rates float with market demand. Not investment advice."
          : "Read-only — live signing isn't enabled on this deployment yet. Rates below are real; depositing is disabled."}
      </div>

      <div className={styles.section}>
        <h3>Stablecoin lending — Jupiter Lend</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Asset</th>
              <th>Supply APY</th>
              <th>Total supplied</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.asset_mint}>
                <td>{t.symbol}</td>
                <td>{t.supply_apy_pct.toFixed(2)}%</td>
                <td>${t.total_supplied_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
              No Solana wallet extension found — install Phantom or Solflare to deposit.
            </span>
          )}
          {wallet.error && <span className={styles.error}>{wallet.error}</span>}
          {actionError && <span className={styles.error}>{actionError}</span>}
          {lastResult && <span className={styles.result}>{lastResult}</span>}
        </div>
      )}

      {config?.trading_enabled && wallet.address && (
        <form className={styles.section} onSubmit={handleSubmit}>
          <div className={styles.form}>
            <label className={styles.field}>
              Asset
              <select value={selected} onChange={(e) => setSelected(e.target.value)}>
                {tokens.map((t) => (
                  <option key={t.asset_mint} value={t.asset_mint}>
                    {t.symbol}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Action
              <select value={action} onChange={(e) => setAction(e.target.value as "deposit" | "withdraw")}>
                <option value="deposit">Deposit</option>
                <option value="withdraw">Withdraw</option>
              </select>
            </label>
            <label className={styles.field}>
              Amount
              <input
                type="number"
                step="any"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <button className={styles.button} type="submit" disabled={submitting}>
              {submitting ? "Submitting…" : action === "deposit" ? "Deposit" : "Withdraw"}
            </button>
          </div>
        </form>
      )}

      {wallet.address && history.length > 0 && (
        <div className={styles.section}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Action</th>
                <th>Amount</th>
                <th>Signature</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {history.map((fill) => (
                <tr key={fill.id}>
                  <td>{fill.action}</td>
                  <td>{fill.amount}</td>
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
