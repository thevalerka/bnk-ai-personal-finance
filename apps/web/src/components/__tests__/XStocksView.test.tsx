import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { XStocksView } from "../XStocksView";
import { SolanaWalletProvider } from "../SolanaWallet";
import { connectSolanaWallet, discoverSolanaWallets } from "@/lib/solanaWallet";
import {
  fetchJupiterConfig,
  fetchSwapQuote,
  fetchUsdcMint,
  fetchXStocks,
  fetchSwapHistory,
  recordSwapFill,
  signAndSendSwap,
} from "@/lib/jupiter";

vi.mock("@/lib/solanaWallet", async () => {
  const actual = await vi.importActual<typeof import("@/lib/solanaWallet")>("@/lib/solanaWallet");
  return { ...actual, discoverSolanaWallets: vi.fn(), connectSolanaWallet: vi.fn() };
});
vi.mock("@/lib/jupiter", () => ({
  fetchJupiterConfig: vi.fn(),
  fetchXStocks: vi.fn(),
  fetchUsdcMint: vi.fn(),
  fetchSwapHistory: vi.fn(),
  fetchSwapQuote: vi.fn(),
  recordSwapFill: vi.fn(),
  signAndSendSwap: vi.fn(),
}));

const mockedDiscover = vi.mocked(discoverSolanaWallets);
const mockedConnect = vi.mocked(connectSolanaWallet);
const mockedConfig = vi.mocked(fetchJupiterConfig);
const mockedXStocks = vi.mocked(fetchXStocks);
const mockedUsdcMint = vi.mocked(fetchUsdcMint);
const mockedHistory = vi.mocked(fetchSwapHistory);
const mockedQuote = vi.mocked(fetchSwapQuote);
const mockedRecordFill = vi.mocked(recordSwapFill);
const mockedSignAndSend = vi.mocked(signAndSendSwap);

const PHANTOM = { id: "phantom", name: "Phantom", provider: {} as never };

const XSTOCKS = [
  {
    symbol: "AAPLx",
    name: "Apple",
    mint: "AAPLmint",
    decimals: 8,
    price_usd: 306.77,
    category: "public_equity" as const,
    note: "note",
  },
  {
    symbol: "VCXx",
    name: "Fundrise Innovation Fund",
    mint: "VCXmint",
    decimals: 8,
    price_usd: 43.82,
    category: "pre_ipo" as const,
    note: "note",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockedDiscover.mockReturnValue([PHANTOM]);
  mockedXStocks.mockResolvedValue(XSTOCKS);
  mockedUsdcMint.mockResolvedValue({ mint: "USDCmint" });
  mockedHistory.mockResolvedValue([]);
});

function renderView() {
  return render(
    <SolanaWalletProvider>
      <XStocksView />
    </SolanaWalletProvider>,
  );
}

describe("XStocksView", () => {
  it("shows a read-only banner and prices, with no wallet UI, when trading is disabled", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: false, platform_fee_bps: 0, configured: false });

    renderView();

    expect(await screen.findByText(/read-only/i)).toBeInTheDocument();
    expect(await screen.findByText("AAPLx")).toBeInTheDocument();
    expect(screen.queryByText(/connect phantom/i)).not.toBeInTheDocument();
  });

  it("labels pre-IPO xStocks distinctly from public-equity ones", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: false, platform_fee_bps: 0, configured: false });

    renderView();

    expect(await screen.findByText("Public-equity xStocks")).toBeInTheDocument();
    expect(await screen.findByText("Pre-IPO / private exposure")).toBeInTheDocument();
    expect(await screen.findByText("VCXx")).toBeInTheDocument();
  });

  it("offers wallet connect once trading is enabled", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: true, platform_fee_bps: 25, configured: true });

    renderView();

    expect(await screen.findByText(/mainnet — real funds/i)).toBeInTheDocument();
    expect(await screen.findByText("Connect Phantom")).toBeInTheDocument();
  });

  it("gets a quote and completes a swap after connecting", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: true, platform_fee_bps: 25, configured: true });
    mockedConnect.mockResolvedValue({ address: "So1ABC", provider: {} as never });
    mockedQuote.mockResolvedValue({
      input_mint: "USDCmint",
      output_mint: "AAPLmint",
      in_amount: "10000000",
      out_amount: "3000000",
      price_impact_pct: 0.05,
      raw_quote: { foo: "bar" },
    });
    mockedSignAndSend.mockResolvedValue("sig-abc123456789");
    mockedRecordFill.mockResolvedValue({
      id: 1,
      wallet_address: "so1abc",
      input_mint: "USDCmint",
      output_mint: "AAPLmint",
      in_amount: "10000000",
      out_amount: "3000000",
      signature: "sig-abc123456789",
      platform_fee_bps: 25,
      created_at: new Date().toISOString(),
    });

    renderView();
    fireEvent.click(await screen.findByText("Connect Phantom"));
    await waitFor(() => expect(screen.getByText("So1ABC")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Get quote"));
    await waitFor(() => expect(mockedQuote).toHaveBeenCalled());
    expect(await screen.findByText(/price impact 0.05%/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Confirm swap"));

    await waitFor(() => expect(mockedSignAndSend).toHaveBeenCalled());
    expect(mockedRecordFill).toHaveBeenCalledWith(
      expect.objectContaining({ walletAddress: "So1ABC", signature: "sig-abc123456789" }),
    );
    expect(await screen.findByText(/Swapped for/)).toBeInTheDocument();
  });
});
