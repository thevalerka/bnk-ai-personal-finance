// Injected Solana wallet connection (docs/DECISIONS.md ADR-0029) — the
// Solana-chain sibling of lib/wallet.ts's EIP-6963 EVM discovery. Solana
// has its own cross-wallet standard (the Wallet Standard,
// wallet-standard:register-wallet events) but implementing that protocol
// from scratch is a bigger surface than this feature needs; Phantom and
// Solflare — the two wallets that matter for xStocks/Jupiter Lend in
// practice — both expose a stable, well-documented injected object
// (`window.phantom.solana`, `window.solflare`), so this does direct
// detection instead, same pragmatic tradeoff wallet.ts already made for
// its own static fallbacks.

export interface SolanaSignedResult {
  signature: string;
}

export interface SolanaProvider {
  publicKey: { toString(): string } | null;
  connect(): Promise<{ publicKey: { toString(): string } }>;
  disconnect?(): Promise<void>;
  // Accepts a serialized (base64-decoded) VersionedTransaction — every
  // caller in this repo deserializes with @solana/web3.js before passing
  // it in, so this stays untyped here rather than pulling that dependency
  // into a file that has no other reason to import it.
  signAndSendTransaction(transaction: unknown): Promise<SolanaSignedResult>;
}

interface PhantomWindow {
  phantom?: { solana?: SolanaProvider };
}

interface SolflareWindow {
  solflare?: SolanaProvider & { isSolflare?: boolean };
}

// Cast rather than a `declare global` augmentation: lib/wallet.ts already
// augments `Window.phantom` for its own (different-shaped) EVM purposes,
// and TS requires every augmentation of the same global property to share
// one exact type — a second, Solana-shaped one here would conflict with
// it. Scoping the shape to a local cast avoids that entirely.
function phantomWindow(): PhantomWindow | undefined {
  return typeof window === "undefined" ? undefined : (window as unknown as PhantomWindow);
}

function solflareWindow(): SolflareWindow | undefined {
  return typeof window === "undefined" ? undefined : (window as unknown as SolflareWindow);
}

export interface SolanaWalletOption {
  id: string;
  name: string;
  provider: SolanaProvider;
}

export function discoverSolanaWallets(): SolanaWalletOption[] {
  const found: SolanaWalletOption[] = [];
  const phantom = phantomWindow()?.phantom?.solana;
  if (phantom) {
    found.push({ id: "phantom", name: "Phantom", provider: phantom });
  }
  const solflare = solflareWindow()?.solflare;
  if (solflare) {
    found.push({ id: "solflare", name: "Solflare", provider: solflare });
  }
  return found;
}

export async function connectSolanaWallet(
  option: SolanaWalletOption,
): Promise<{ address: string; provider: SolanaProvider }> {
  const { publicKey } = await option.provider.connect();
  if (!publicKey) {
    throw new Error("Wallet connection was rejected.");
  }
  return { address: publicKey.toString(), provider: option.provider };
}

/** Converts a human-entered decimal amount ("12.5") to the smallest-unit
 * integer string Jupiter's APIs expect, without floating-point precision
 * loss on large amounts (string-based decimal shift, not `* 10**n`). */
export function toSmallestUnit(amount: string, decimals: number): string {
  const trimmed = amount.trim();
  const [whole = "0", frac = ""] = trimmed.split(".");
  const paddedFrac = (frac + "0".repeat(decimals)).slice(0, decimals);
  const combined = `${whole}${paddedFrac}`.replace(/^0+(?=\d)/, "");
  return combined.length > 0 ? combined : "0";
}

/** Inverse of toSmallestUnit — smallest-unit integer string to a display
 * decimal string, for rendering amounts the API returns. */
export function fromSmallestUnit(amount: string, decimals: number): string {
  const padded = amount.padStart(decimals + 1, "0");
  const whole = padded.slice(0, padded.length - decimals);
  const frac = padded.slice(padded.length - decimals).replace(/0+$/, "");
  return frac.length > 0 ? `${whole}.${frac}` : whole;
}
