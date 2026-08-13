import type { ReactNode } from "react";
import styles from "./Block.module.css";

export function Block({
  title,
  source,
  minHeight,
  children,
}: {
  title: string;
  source?: string;
  minHeight?: number;
  children: ReactNode;
}) {
  return (
    <section className={styles.block} style={{ minHeight }}>
      <header className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
        {source ? <span className={styles.sourceBadge}>{source}</span> : null}
      </header>
      <div className={styles.body}>{children}</div>
    </section>
  );
}

export function BlockSkeleton({ title, minHeight }: { title: string; minHeight?: number }) {
  return (
    <section className={styles.block} style={{ minHeight }}>
      <header className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
      </header>
      <div className={styles.body}>
        <div className={styles.skeleton} />
      </div>
    </section>
  );
}

export function Unavailable({ reason }: { reason?: string }) {
  return (
    <div className={styles.unavailable}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>{reason ?? "No live data reachable for this block right now."}</span>
    </div>
  );
}
