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
      {reason ?? "No live data reachable for this block right now."}
    </div>
  );
}
