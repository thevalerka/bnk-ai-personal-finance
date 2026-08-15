"use client";

import { useEffect, useState } from "react";
import styles from "./ThemeToggle.module.css";

type Theme = "light" | "dark";
const STORAGE_KEY = "amt-theme";

// The actual light/dark decision at first paint is made by the inline
// script in layout.tsx (runs before hydration, no flash) — this component
// only needs to read the DOM attribute that script already set, then keep
// it and localStorage in sync on toggle.
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  if (theme === null) {
    // Matches the inline script's default until mount, so nothing shifts.
    return <button type="button" className={styles.toggle} aria-hidden="true" tabIndex={-1} />;
  }

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.55 1.55M18.25 18.25l1.55 1.55M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.55-1.55M18.25 5.75l1.55-1.55"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      )}
    </button>
  );
}
