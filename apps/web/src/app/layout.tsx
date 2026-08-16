import type { Metadata } from "next";
import { Space_Grotesk, JetBrains_Mono } from "next/font/google";
import { ExplainPanelProvider } from "@/components/ExplainPanel";
import { PanelPrefsProvider } from "@/components/PanelPrefs";
import { WalletProvider } from "@/components/Wallet";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-data",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Adaptive Markets Terminal",
  description: "A market dashboard that reallocates its own layout from what you actually look at.",
};

// Runs before hydration (blocking, in <head>) so the persisted theme
// applies to the very first paint — without this, the page would flash the
// default light theme for a frame before a dark-theme visitor's choice
// kicks in on mount (ThemeToggle.tsx). Default is light per ADR-0014;
// unlike ADR-0013's accepted layout flash, this one is fully avoidable
// since the theme choice lives in localStorage, not a server round-trip.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem("amt-theme");
    if (stored === "dark") document.documentElement.setAttribute("data-theme", "dark");
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${jetbrainsMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <WalletProvider>
          <PanelPrefsProvider>
            <ExplainPanelProvider>{children}</ExplainPanelProvider>
          </PanelPrefsProvider>
        </WalletProvider>
      </body>
    </html>
  );
}
