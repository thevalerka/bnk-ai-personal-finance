import styles from "./Shell.module.css";

// Prompt bar is intentionally non-functional in P2 — the agent loop that
// answers it lands in phase 4 (docs/PLAN.md P4). Persona switcher is a
// static label for the same reason: it needs the interest-vector model
// from phase 3 (attention engine) before it can do anything.
export function Shell() {
  return (
    <header className={styles.header}>
      <h1 className={styles.brand}>
        <span className={styles.dot} aria-hidden="true" />
        Adaptive Markets <span className={styles.brandAccent}>Terminal</span>
      </h1>
      <nav className={styles.nav}>
        <span className={styles.navActive}>Dashboard</span>
        <span>Architecture · soon</span>
        <span>Notes · soon</span>
      </nav>
      <div className={styles.promptBar}>
        <svg
          className={styles.promptIcon}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M11 4a7 7 0 1 0 4.9 12.02l4.54 4.54 1.41-1.41-4.54-4.54A7 7 0 0 0 11 4Zm-5 7a5 5 0 1 1 10 0 5 5 0 0 1-10 0Z"
            fill="currentColor"
          />
        </svg>
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
