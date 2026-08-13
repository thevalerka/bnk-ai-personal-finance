import { fetchNews } from "@/lib/market";
import styles from "./NewsList.module.css";

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export async function NewsList() {
  const items = await fetchNews();

  if (!items || items.length === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13 }}>News unavailable — no provider reachable.</p>;
  }

  return (
    <ul className={styles.list}>
      {items.slice(0, 10).map((item) => (
        <li key={item.id} className={styles.item}>
          <a href={item.url} target="_blank" rel="noreferrer" className={styles.headline}>
            {item.headline}
          </a>
          <div className={styles.meta}>
            <span>{item.source}</span>
            <span>{relativeTime(item.ts)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
