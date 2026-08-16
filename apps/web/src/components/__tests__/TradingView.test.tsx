import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { TradingView } from "../TradingView";
import { WalletProvider } from "../Wallet";
import { connectWallet, discoverWallets } from "@/lib/wallet";
import { approveBuilderFeeOnChain, fetchMidPrice, placeOrder } from "@/lib/hyperliquid";
import { fetchOrderHistory, fetchTradingConfig, recordApproval, recordFill } from "@/lib/trading";

vi.mock("@/lib/wallet", () => ({
  discoverWallets: vi.fn(),
  connectWallet: vi.fn(),
}));
vi.mock("@/lib/hyperliquid", () => ({
  approveBuilderFeeOnChain: vi.fn(),
  fetchMidPrice: vi.fn(),
  placeOrder: vi.fn(),
}));
vi.mock("@/lib/trading", () => ({
  fetchTradingConfig: vi.fn(),
  recordApproval: vi.fn(),
  recordFill: vi.fn(),
  fetchOrderHistory: vi.fn(),
}));

const mockedDiscoverWallets = vi.mocked(discoverWallets);
const mockedConnectWallet = vi.mocked(connectWallet);
const METAMASK = { id: "io.metamask", name: "MetaMask", provider: {} as never };
const mockedApprove = vi.mocked(approveBuilderFeeOnChain);
const mockedFetchMidPrice = vi.mocked(fetchMidPrice);
const mockedPlaceOrder = vi.mocked(placeOrder);
const mockedFetchTradingConfig = vi.mocked(fetchTradingConfig);
const mockedRecordApproval = vi.mocked(recordApproval);
const mockedRecordFill = vi.mocked(recordFill);
const mockedFetchOrderHistory = vi.mocked(fetchOrderHistory);

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockedDiscoverWallets.mockResolvedValue([]);
});

const CONFIG = {
  builder_address: "0xBUILDER",
  builder_fee_tenths_bp: 10,
  testnet_base_url: "https://api.hyperliquid-testnet.xyz",
  configured: true,
};

function renderView() {
  return render(
    <WalletProvider>
      <TradingView />
    </WalletProvider>,
  );
}

// discoverWallets/connectWallet must already be mocked before renderView()
// runs — TradingView discovers wallets in a mount-time effect, so setting
// the mock afterward misses that first call.
async function connect() {
  fireEvent.click(await screen.findByText("Connect MetaMask"));
  await waitFor(() => expect(screen.getByText("0xABCDEF")).toBeInTheDocument());
}

describe("TradingView", () => {
  it("shows an unavailable message when trading isn't configured", async () => {
    mockedFetchTradingConfig.mockResolvedValue({ ...CONFIG, configured: false });

    renderView();

    expect(await screen.findByText(/trading isn't configured yet/i)).toBeInTheDocument();
  });

  it("shows a message when no wallet extension is detected", async () => {
    mockedFetchTradingConfig.mockResolvedValue(CONFIG);

    renderView();

    expect(await screen.findByText(/no wallet extension found/i)).toBeInTheDocument();
  });

  it("shows a connect button per detected wallet once configured", async () => {
    mockedFetchTradingConfig.mockResolvedValue(CONFIG);
    mockedDiscoverWallets.mockResolvedValue([
      METAMASK,
      { id: "app.phantom", name: "Phantom", provider: {} as never },
    ]);

    renderView();

    expect(await screen.findByText("Connect MetaMask")).toBeInTheDocument();
    expect(await screen.findByText("Connect Phantom")).toBeInTheDocument();
  });

  it("shows the approve step after connecting, and the order form after approving", async () => {
    mockedFetchTradingConfig.mockResolvedValue(CONFIG);
    mockedFetchOrderHistory.mockResolvedValue([]);
    mockedDiscoverWallets.mockResolvedValue([METAMASK]);
    mockedConnectWallet.mockResolvedValue({ address: "0xABCDEF", client: {} as never });
    mockedApprove.mockResolvedValue(undefined);
    mockedRecordApproval.mockResolvedValue({});

    renderView();
    await connect();

    const approveButton = await screen.findByText("Approve builder fee (testnet)");
    fireEvent.click(approveButton);

    await waitFor(() => expect(mockedApprove).toHaveBeenCalledWith({}, "0xBUILDER", 10));
    expect(mockedRecordApproval).toHaveBeenCalledWith("0xABCDEF", 10);
    expect(await screen.findByText("Place order")).toBeInTheDocument();
  });

  it("submits a market order and records the fill", async () => {
    mockedFetchTradingConfig.mockResolvedValue(CONFIG);
    mockedFetchOrderHistory.mockResolvedValue([]);
    mockedDiscoverWallets.mockResolvedValue([METAMASK]);
    mockedConnectWallet.mockResolvedValue({ address: "0xABCDEF", client: {} as never });
    mockedApprove.mockResolvedValue(undefined);
    mockedRecordApproval.mockResolvedValue({});
    mockedFetchMidPrice.mockResolvedValue(65000);
    mockedPlaceOrder.mockResolvedValue({ orderId: 42, resting: false });
    mockedRecordFill.mockResolvedValue({
      id: 1,
      wallet_address: "0xabcdef",
      coin: "BTC",
      side: "buy",
      size: 0.01,
      price: 65650,
      builder_fee_tenths_bp: 10,
      created_at: new Date().toISOString(),
    });

    renderView();
    await connect();
    fireEvent.click(await screen.findByText("Approve builder fee (testnet)"));
    await screen.findByText("Place order");

    fireEvent.click(screen.getByText("Place order"));

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedRecordFill).toHaveBeenCalledWith(
      expect.objectContaining({ walletAddress: "0xABCDEF", coin: "BTC", orderId: 42 }),
    );
    expect(await screen.findByText(/Order #42 filled\./)).toBeInTheDocument();
  });
});
