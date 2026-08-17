import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { LendView } from "../LendView";
import { SolanaWalletProvider } from "../SolanaWallet";
import { connectSolanaWallet, discoverSolanaWallets } from "@/lib/solanaWallet";
import {
  fetchJupiterConfig,
  fetchLendHistory,
  fetchLendTokens,
  recordLendFill,
  signAndSendLend,
} from "@/lib/jupiter";

vi.mock("@/lib/solanaWallet", async () => {
  const actual = await vi.importActual<typeof import("@/lib/solanaWallet")>("@/lib/solanaWallet");
  return { ...actual, discoverSolanaWallets: vi.fn(), connectSolanaWallet: vi.fn() };
});
vi.mock("@/lib/jupiter", () => ({
  fetchJupiterConfig: vi.fn(),
  fetchLendTokens: vi.fn(),
  fetchLendHistory: vi.fn(),
  recordLendFill: vi.fn(),
  signAndSendLend: vi.fn(),
}));

const mockedDiscover = vi.mocked(discoverSolanaWallets);
const mockedConnect = vi.mocked(connectSolanaWallet);
const mockedConfig = vi.mocked(fetchJupiterConfig);
const mockedTokens = vi.mocked(fetchLendTokens);
const mockedHistory = vi.mocked(fetchLendHistory);
const mockedRecordFill = vi.mocked(recordLendFill);
const mockedSignAndSend = vi.mocked(signAndSendLend);

const PHANTOM = { id: "phantom", name: "Phantom", provider: {} as never };
const USDC_TOKEN = { asset_mint: "USDCmint", symbol: "USDC", decimals: 6, supply_apy_pct: 3.86, total_supplied_usd: 1_000_000 };

beforeEach(() => {
  vi.clearAllMocks();
  mockedDiscover.mockReturnValue([PHANTOM]);
  mockedTokens.mockResolvedValue([USDC_TOKEN]);
  mockedHistory.mockResolvedValue([]);
});

function renderView() {
  return render(
    <SolanaWalletProvider>
      <LendView />
    </SolanaWalletProvider>,
  );
}

describe("LendView", () => {
  it("shows a read-only banner and real APYs, with no wallet UI, when trading is disabled", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: false, platform_fee_bps: 0, configured: false });

    renderView();

    expect(await screen.findByText(/read-only/i)).toBeInTheDocument();
    expect(await screen.findByText("3.86%")).toBeInTheDocument();
    expect(screen.queryByText(/connect phantom/i)).not.toBeInTheDocument();
  });

  it("completes a deposit after connecting", async () => {
    mockedConfig.mockResolvedValue({ trading_enabled: true, platform_fee_bps: 0, configured: false });
    mockedConnect.mockResolvedValue({ address: "So1ABC", provider: {} as never });
    mockedSignAndSend.mockResolvedValue("sig-lend-abc123456");
    mockedRecordFill.mockResolvedValue({
      id: 1,
      wallet_address: "so1abc",
      asset_mint: "USDCmint",
      action: "deposit",
      amount: "100000000",
      signature: "sig-lend-abc123456",
      created_at: new Date().toISOString(),
    });

    renderView();
    fireEvent.click(await screen.findByText("Connect Phantom"));
    await waitFor(() => expect(screen.getByText("So1ABC")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Deposit" }));

    await waitFor(() => expect(mockedSignAndSend).toHaveBeenCalled());
    expect(mockedSignAndSend).toHaveBeenCalledWith(
      {},
      expect.objectContaining({ walletAddress: "So1ABC", assetMint: "USDCmint", action: "deposit", amount: "100000000" }),
    );
    expect(mockedRecordFill).toHaveBeenCalledWith(
      expect.objectContaining({ walletAddress: "So1ABC", signature: "sig-lend-abc123456" }),
    );
    expect(await screen.findByText(/Deposited 100 USDC/)).toBeInTheDocument();
  });
});
