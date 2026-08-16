// Injected EVM wallet connection, via viem. First web3 dependency in the
// repo (docs/DECISIONS.md ADR-0028) — deliberately kept separate from
// lib/hyperliquid.ts (which builds on top of this) so this file has zero
// Hyperliquid-specific knowledge: it only knows how to find wallets and get
// an address + signer out of whichever one the visitor picks.
//
// No RPC network switch is needed: Hyperliquid signing is plain
// eth_signTypedData_v4, not an action scoped to a particular chain's RPC —
// a wallet never needs "Hyperliquid" added as a network.
//
// Discovery uses EIP-6963 (https://eips.ethereum.org/EIPS/eip-6963), the
// standard both MetaMask and Phantom support specifically to fix the
// long-standing `window.ethereum` collision: with more than one extension
// installed, whichever wallet's script runs last silently claims
// `window.ethereum`, so a plain `window.ethereum` check can find the wrong
// wallet or miss one entirely. Static fallbacks for `window.ethereum` and
// Phantom's own non-colliding `window.phantom.ethereum` namespace
// (confirmed via Phantom's own docs) cover wallets that haven't adopted
// EIP-6963 yet.

import { createWalletClient, custom, type EIP1193Provider, type WalletClient } from "viem";

interface Eip6963ProviderInfo {
  uuid: string;
  name: string;
  icon: string;
  rdns: string;
}

interface Eip6963ProviderDetail {
  info: Eip6963ProviderInfo;
  provider: EIP1193Provider;
}

declare global {
  interface WindowEventMap {
    "eip6963:announceProvider": CustomEvent<Eip6963ProviderDetail>;
  }
  interface Window {
    ethereum?: EIP1193Provider & { isMetaMask?: boolean };
    phantom?: { ethereum?: EIP1193Provider };
  }
}

export interface WalletOption {
  id: string;
  name: string;
  icon?: string;
  provider: EIP1193Provider;
}

/** Every EIP-1193 wallet the browser currently has available. Resolves
 * once EIP-6963 announcements have had a short window to arrive (they're
 * dispatched synchronously in response to the request event, so this
 * doesn't meaningfully delay the picker) plus the two well-known static
 * fallbacks, added only if that wallet didn't already announce itself. */
export function discoverWallets(): Promise<WalletOption[]> {
  if (typeof window === "undefined") return Promise.resolve([]);

  return new Promise((resolve) => {
    const found = new Map<string, WalletOption>();

    function onAnnounce(event: WindowEventMap["eip6963:announceProvider"]) {
      const { info, provider } = event.detail;
      found.set(info.rdns, { id: info.rdns, name: info.name, icon: info.icon, provider });
    }

    window.addEventListener("eip6963:announceProvider", onAnnounce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));

    setTimeout(() => {
      window.removeEventListener("eip6963:announceProvider", onAnnounce);

      const alreadyAnnounced = (needle: string) =>
        Array.from(found.values()).some((w) => w.name.toLowerCase().includes(needle));

      if (window.phantom?.ethereum && !alreadyAnnounced("phantom")) {
        found.set("app.phantom.fallback", {
          id: "app.phantom.fallback",
          name: "Phantom",
          provider: window.phantom.ethereum,
        });
      }
      if (window.ethereum && !alreadyAnnounced("metamask") && !alreadyAnnounced("phantom")) {
        found.set("io.metamask.fallback", {
          id: "io.metamask.fallback",
          name: window.ethereum.isMetaMask ? "MetaMask" : "Injected wallet",
          provider: window.ethereum,
        });
      }

      resolve(Array.from(found.values()));
    }, 200);
  });
}

export async function connectWallet(
  option: WalletOption,
): Promise<{ address: `0x${string}`; client: WalletClient }> {
  // Two-step: the first client has no bound account, just enough to prompt
  // eth_requestAccounts. The SDK's signing helpers (lib/hyperliquid.ts)
  // call wallet.signTypedData with no per-call account, so the client
  // actually used for signing needs one bound at construction time.
  const probe = createWalletClient({ transport: custom(option.provider) });
  const [address] = await probe.requestAddresses();
  if (!address) {
    throw new Error("Wallet connection was rejected.");
  }
  const client = createWalletClient({ account: address, transport: custom(option.provider) });
  return { address, client };
}
