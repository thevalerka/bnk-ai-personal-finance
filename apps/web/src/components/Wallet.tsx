"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import type { WalletClient } from "viem";
import { connectWallet, discoverWallets, type WalletOption } from "@/lib/wallet";

// Only the public address is ever persisted — there is no secret to leak.
// Records which addresses have already sent an on-chain builder-fee
// approval so the "Approve" step doesn't need to be shown again once
// confirmed; purely a UX shortcut, not a security boundary — Hyperliquid
// itself is the real source of truth for whether an approval is active.
const APPROVED_KEY = "amt-wallet-approved";

function loadApproved(): string[] {
  try {
    const raw = window.localStorage.getItem(APPROVED_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

interface WalletContextValue {
  address: `0x${string}` | null;
  client: WalletClient | null;
  connecting: boolean;
  error: string | null;
  builderApproved: boolean;
  availableWallets: WalletOption[];
  refreshWallets: () => Promise<void>;
  connect: (walletId: string) => Promise<void>;
  disconnect: () => void;
  markBuilderApproved: () => void;
}

const WalletContext = createContext<WalletContextValue | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const [address, setAddress] = useState<`0x${string}` | null>(null);
  const [client, setClient] = useState<WalletClient | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approved, setApproved] = useState<string[]>([]);
  const [availableWallets, setAvailableWallets] = useState<WalletOption[]>([]);

  const refreshWallets = useCallback(async () => {
    setAvailableWallets(await discoverWallets());
  }, []);

  const connect = useCallback(
    async (walletId: string) => {
      setConnecting(true);
      setError(null);
      try {
        const options = availableWallets.length > 0 ? availableWallets : await discoverWallets();
        const option = options.find((w) => w.id === walletId);
        if (!option) {
          setError("That wallet is no longer available — refresh and try again.");
          return;
        }
        const { address: addr, client: walletClient } = await connectWallet(option);
        setAddress(addr);
        setClient(walletClient);
        setApproved(loadApproved());
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
    setClient(null);
    setError(null);
  }, []);

  const markBuilderApproved = useCallback(() => {
    if (!address) return;
    const lowered = address.toLowerCase();
    setApproved((prev) => {
      if (prev.includes(lowered)) return prev;
      const next = [...prev, lowered];
      window.localStorage.setItem(APPROVED_KEY, JSON.stringify(next));
      return next;
    });
  }, [address]);

  const builderApproved = address ? approved.includes(address.toLowerCase()) : false;

  return (
    <WalletContext.Provider
      value={{
        address,
        client,
        connecting,
        error,
        builderApproved,
        availableWallets,
        refreshWallets,
        connect,
        disconnect,
        markBuilderApproved,
      }}
    >
      {children}
    </WalletContext.Provider>
  );
}

export function useWallet(): WalletContextValue {
  const ctx = useContext(WalletContext);
  if (!ctx) throw new Error("useWallet must be used within WalletProvider");
  return ctx;
}
