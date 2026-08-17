import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SolanaWalletProvider, useSolanaWallet } from "../SolanaWallet";
import { connectSolanaWallet, discoverSolanaWallets } from "@/lib/solanaWallet";

vi.mock("@/lib/solanaWallet", async () => {
  const actual = await vi.importActual<typeof import("@/lib/solanaWallet")>("@/lib/solanaWallet");
  return { ...actual, discoverSolanaWallets: vi.fn(), connectSolanaWallet: vi.fn() };
});

const mockedDiscover = vi.mocked(discoverSolanaWallets);
const mockedConnect = vi.mocked(connectSolanaWallet);

const PHANTOM = { id: "phantom", name: "Phantom", provider: {} as never };
const SOLFLARE = { id: "solflare", name: "Solflare", provider: {} as never };

beforeEach(() => {
  vi.clearAllMocks();
  mockedDiscover.mockReturnValue([PHANTOM, SOLFLARE]);
});

function Consumer() {
  const wallet = useSolanaWallet();
  return (
    <div>
      <span data-testid="address">{wallet.address ?? "none"}</span>
      <span data-testid="error">{wallet.error ?? ""}</span>
      <span data-testid="wallets">{wallet.availableWallets.map((w) => w.name).join(",")}</span>
      <button onClick={wallet.refreshWallets}>refresh</button>
      <button onClick={() => wallet.connect("phantom")}>connect phantom</button>
      <button onClick={wallet.disconnect}>disconnect</button>
    </div>
  );
}

describe("SolanaWalletProvider", () => {
  it("starts disconnected with no wallets discovered yet", () => {
    render(
      <SolanaWalletProvider>
        <Consumer />
      </SolanaWalletProvider>,
    );
    expect(screen.getByTestId("address")).toHaveTextContent("none");
    expect(screen.getByTestId("wallets")).toHaveTextContent("");
  });

  it("discovers wallets on demand", () => {
    render(
      <SolanaWalletProvider>
        <Consumer />
      </SolanaWalletProvider>,
    );
    fireEvent.click(screen.getByText("refresh"));

    expect(screen.getByTestId("wallets")).toHaveTextContent("Phantom,Solflare");
  });

  it("connects with the chosen wallet", async () => {
    mockedConnect.mockResolvedValue({ address: "So1AAA111", provider: {} as never });

    render(
      <SolanaWalletProvider>
        <Consumer />
      </SolanaWalletProvider>,
    );
    fireEvent.click(screen.getByText("connect phantom"));

    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("So1AAA111"));
    expect(mockedConnect).toHaveBeenCalledWith(PHANTOM);
  });

  it("surfaces an error when the chosen wallet id no longer exists", async () => {
    mockedDiscover.mockReturnValue([]);

    render(
      <SolanaWalletProvider>
        <Consumer />
      </SolanaWalletProvider>,
    );
    fireEvent.click(screen.getByText("connect phantom"));

    await waitFor(() => expect(screen.getByTestId("error")).not.toHaveTextContent(""));
    expect(mockedConnect).not.toHaveBeenCalled();
  });

  it("disconnect clears the address", async () => {
    mockedConnect.mockResolvedValue({ address: "So1AAA111", provider: {} as never });

    render(
      <SolanaWalletProvider>
        <Consumer />
      </SolanaWalletProvider>,
    );
    fireEvent.click(screen.getByText("connect phantom"));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("So1AAA111"));

    fireEvent.click(screen.getByText("disconnect"));
    expect(screen.getByTestId("address")).toHaveTextContent("none");
  });
});
