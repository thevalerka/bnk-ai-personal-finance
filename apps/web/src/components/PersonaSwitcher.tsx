"use client";

import { useEffect, useRef, useState } from "react";
import { fetchMe, fetchPersonas, resetProfile, viewAsPersona, type PersonaOut } from "@/lib/attention";
import styles from "./PersonaSwitcher.module.css";

// docs/PLAN.md section 1: "'View as' persona switcher ... Loads a
// pre-seeded interest vector so a visitor can see the personalization work
// in one click." A full page reload after switching is deliberate — it's
// the simplest way to get every part of the page (DynamicGrid's layout
// fetch, and eventually the suggestion rail) to pick up the new profile
// cookie consistently, without a cross-tree client state manager.
export function PersonaSwitcher() {
  const [personas, setPersonas] = useState<PersonaOut[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchPersonas().then((list) => list && setPersonas(list));
    void fetchMe().then((me) => me && setCurrent(me.persona));
  }, []);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  async function select(name: string | null) {
    setSwitching(true);
    const result = name ? await viewAsPersona(name) : await resetProfile();
    if (result) {
      window.location.reload();
    } else {
      setSwitching(false);
      setOpen(false);
    }
  }

  const currentLabel = current ? (personas.find((p) => p.name === current)?.label ?? current) : "Default";

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        View as: <span className={styles.value}>{switching ? "…" : currentLabel}</span>
      </button>
      {open ? (
        <ul className={styles.menu} role="listbox">
          <li>
            <button
              type="button"
              role="option"
              className={styles.option}
              onClick={() => void select(null)}
              aria-selected={current === null}
            >
              <span className={styles.optionLabel}>Default</span>
              <span className={styles.optionDesc}>Your own organic browsing history</span>
            </button>
          </li>
          {personas.map((p) => (
            <li key={p.name}>
              <button
                type="button"
                role="option"
                className={styles.option}
                onClick={() => void select(p.name)}
                aria-selected={current === p.name}
              >
                <span className={styles.optionLabel}>{p.label}</span>
                <span className={styles.optionDesc}>{p.description}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
