import { fetchNews } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./NewsList.module.css";

// .source's CSS only capitalizes the first letter of the whole string
// (text-transform: capitalize doesn't split on "_") — "federal_reserve"
// rendered as "Federal_reserve" until this replaces underscores with
// spaces first. Surfaced live while building the stock detail page, where
// sec_edgar's underscore made the same pre-existing bug hard to miss.
function formatSource(source: string): string {
  return source.replace(/_/g, " ");
}

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
    return <Unavailable reason="News unavailable — no provider reachable." />;
  }

  return (
    <ul className={styles.list}>
      {items.slice(0, 10).map((item) => (
        <li key={item.id} className={styles.item}>
          <a href={item.url} target="_blank" rel="noreferrer" className={styles.headline}>
            {item.headline}
            <svg className={styles.linkIcon} width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M7 17 17 7M17 7H9m8 0v8"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </a>
          <div className={styles.meta}>
            <span className={styles.source}>{formatSource(item.source)}</span>
            <span>{relativeTime(item.ts)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
