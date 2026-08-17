"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import {
  connectSolanaWallet,
  discoverSolanaWallets,
  type SolanaProvider,
  type SolanaWalletOption,
} from "@/lib/solanaWallet";

interface SolanaWalletContextValue {
  address: string | null;
  provider: SolanaProvider | null;
  connecting: boolean;
  error: string | null;
  availableWallets: SolanaWalletOption[];
  refreshWallets: () => void;
  connect: (walletId: string) => Promise<void>;
  disconnect: () => void;
}

const SolanaWalletContext = createContext<SolanaWalletContextValue | null>(null);

// Shared by both /xstocks and /lend (docs/DECISIONS.md ADR-0029) — same
// one-connection-per-session shape as components/Wallet.tsx's EVM
// counterpart, just Solana-side (SolanaWalletProvider mounts once in
// layout.tsx, same as WalletProvider).
export function SolanaWalletProvider({ children }: { children: ReactNode }) {
  const [address, setAddress] = useState<string | null>(null);
  const [provider, setProvider] = useState<SolanaProvider | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableWallets, setAvailableWallets] = useState<SolanaWalletOption[]>([]);

  const refreshWallets = useCallback(() => {
    setAvailableWallets(discoverSolanaWallets());
  }, []);

  const connect = useCallback(
    async (walletId: string) => {
      setConnecting(true);
      setError(null);
      try {
        const options = availableWallets.length > 0 ? availableWallets : discoverSolanaWallets();
        const option = options.find((w) => w.id === walletId);
        if (!option) {
          setError("That wallet is no longer available — refresh and try again.");
          return;
        }
        const { address: addr, provider: connectedProvider } = await connectSolanaWallet(option);
        setAddress(addr);
        setProvider(connectedProvider);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Wallet connection failed.");
      } finally {
        setConnecting(false);
      }
    },
    [availableWallets],
  );

  const disconnect = useCallback(() => {
    setAddress(null);
    setProvider(null);
    setError(null);
  }, []);

  return (
    <SolanaWalletContext.Provider
      value={{ address, provider, connecting, error, availableWallets, refreshWallets, connect, disconnect }}
    >
      {children}
    </SolanaWalletContext.Provider>
  );
}

export function useSolanaWallet(): SolanaWalletContextValue {
  const ctx = useContext(SolanaWalletContext);
  if (!ctx) throw new Error("useSolanaWallet must be used within SolanaWalletProvider");
  return ctx;
}
