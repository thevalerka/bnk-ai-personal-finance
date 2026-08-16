import Link from "next/link";
import { PersonaSwitcher } from "./PersonaSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { PanelRestoreTray } from "./PanelRestoreTray";
import { PromptBar } from "./PromptBar";
import styles from "./Shell.module.css";

// Persona switcher (phase 3, PersonaSwitcher.tsx / apps/api's
// /profile/persona) and the prompt bar (phase 4, PromptBar.tsx / apps/api's
// /agent/stream) are both real.
export function Shell() {
  return (
    <header className={styles.header}>
      <h1 className={styles.brand}>
        <span className={styles.dot} aria-hidden="true" />
        Adaptive Markets <span className={styles.brandAccent}>Terminal</span>
      </h1>
      <nav className={styles.nav}>
        <span className={styles.navActive}>Dashboard</span>
        <Link href="/trade" className={styles.navLink}>
          Trade · testnet
        </Link>
        <span>Architecture · soon</span>
        <span>Notes · soon</span>
      </nav>
      <PromptBar />
      <PanelRestoreTray />
      <ThemeToggle />
      <PersonaSwitcher />
    </header>
  );
}
