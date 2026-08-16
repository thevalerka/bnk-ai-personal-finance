import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useWallet, WalletProvider } from "../Wallet";
import { connectWallet, discoverWallets } from "@/lib/wallet";

vi.mock("@/lib/wallet", () => ({
  discoverWallets: vi.fn(),
  connectWallet: vi.fn(),
}));

const mockedDiscoverWallets = vi.mocked(discoverWallets);
const mockedConnectWallet = vi.mocked(connectWallet);

const METAMASK = { id: "io.metamask", name: "MetaMask", provider: {} as never };
const PHANTOM = { id: "app.phantom", name: "Phantom", provider: {} as never };

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockedDiscoverWallets.mockResolvedValue([METAMASK, PHANTOM]);
});

function Consumer() {
  const wallet = useWallet();
  return (
    <div>
      <span data-testid="address">{wallet.address ?? "none"}</span>
      <span data-testid="approved">{wallet.builderApproved ? "yes" : "no"}</span>
      <span data-testid="error">{wallet.error ?? ""}</span>
      <span data-testid="wallets">{wallet.availableWallets.map((w) => w.name).join(",")}</span>
      <button onClick={wallet.refreshWallets}>refresh</button>
      <button onClick={() => wallet.connect("io.metamask")}>connect metamask</button>
      <button onClick={() => wallet.connect("app.phantom")}>connect phantom</button>
      <button onClick={wallet.disconnect}>disconnect</button>
      <button onClick={wallet.markBuilderApproved}>approve</button>
    </div>
  );
}

describe("WalletProvider", () => {
  it("starts disconnected with no wallets discovered yet", () => {
    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    expect(screen.getByTestId("address")).toHaveTextContent("none");
    expect(screen.getByTestId("wallets")).toHaveTextContent("");
  });

  it("discovers wallets on demand", async () => {
    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("refresh"));

    await waitFor(() => expect(screen.getByTestId("wallets")).toHaveTextContent("MetaMask,Phantom"));
  });

  it("connects with the chosen wallet (MetaMask)", async () => {
    mockedConnectWallet.mockResolvedValue({ address: "0xAAA111", client: {} as never });

    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("refresh"));
    await waitFor(() => expect(screen.getByTestId("wallets")).toHaveTextContent("MetaMask"));

    fireEvent.click(screen.getByText("connect metamask"));

    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("0xAAA111"));
    expect(mockedConnectWallet).toHaveBeenCalledWith(METAMASK);
  });

  it("connects with the chosen wallet (Phantom)", async () => {
    mockedConnectWallet.mockResolvedValue({ address: "0xBBB222", client: {} as never });

    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("connect phantom"));

    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("0xBBB222"));
    expect(mockedConnectWallet).toHaveBeenCalledWith(PHANTOM);
  });

  it("surfaces an error when the chosen wallet id no longer exists", async () => {
    mockedDiscoverWallets.mockResolvedValue([]);

    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("connect metamask"));

    await waitFor(() => expect(screen.getByTestId("error")).not.toHaveTextContent(""));
    expect(mockedConnectWallet).not.toHaveBeenCalled();
  });

  it("disconnect clears the address", async () => {
    mockedConnectWallet.mockResolvedValue({ address: "0xAAA111", client: {} as never });

    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("connect metamask"));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("0xAAA111"));

    fireEvent.click(screen.getByText("disconnect"));
    expect(screen.getByTestId("address")).toHaveTextContent("none");
  });

  it("marks the connected address as builder-approved", async () => {
    mockedConnectWallet.mockResolvedValue({ address: "0xAAA111", client: {} as never });

    render(
      <WalletProvider>
        <Consumer />
      </WalletProvider>,
    );
    fireEvent.click(screen.getByText("connect metamask"));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("0xAAA111"));

    expect(screen.getByTestId("approved")).toHaveTextContent("no");
    fireEvent.click(screen.getByText("approve"));
    expect(screen.getByTestId("approved")).toHaveTextContent("yes");
  });
});
