import styles from "./Shell.module.css";

// Prompt bar is intentionally non-functional in P2 — the agent loop that
// answers it lands in phase 4 (docs/PLAN.md P4). Persona switcher is a
// static label for the same reason: it needs the interest-vector model
// from phase 3 (attention engine) before it can do anything.
export function Shell() {
  return (
    <header className={styles.header}>
      <h1 className={styles.brand}>
        Adaptive Markets <span>Terminal</span>
      </h1>
      <nav className={styles.nav}>
        <span>Dashboard</span>
        <span>Architecture · soon</span>
        <span>Notes · soon</span>
      </nav>
      <div className={styles.promptBar}>
        <input
          aria-label="Ask the terminal"
          className={styles.promptInput}
          placeholder="Ask the terminal — coming in phase 4"
          disabled
        />
      </div>
      <div className={styles.persona}>View as: Default</div>
    </header>
  );
}
