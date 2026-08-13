import { existsSync, readFileSync } from "fs";
import { join } from "path";
import type { NextConfig } from "next";

// Next.js only auto-loads files literally named .env*. We deliberately don't
// use that name (see docs/DECISIONS.md ADR-0010), so load our own .ratx*
// files here, in the same low-to-high precedence order Next.js uses for
// .env* — later files win, and a var already set in the real shell
// environment is never overridden.
function loadRatxEnv(): void {
  const shellKeys = new Set(Object.keys(process.env));
  const nodeEnv = process.env.NODE_ENV ?? "development";
  const candidates = [".ratx", `.ratx.${nodeEnv}`, ".ratx.local", `.ratx.${nodeEnv}.local`];

  for (const name of candidates) {
    const path = join(__dirname, name);
    if (!existsSync(path)) continue;

    for (const line of readFileSync(path, "utf-8").split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      if (shellKeys.has(key)) continue;
      process.env[key] = trimmed.slice(eq + 1).trim();
    }
  }
}

loadRatxEnv();

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
