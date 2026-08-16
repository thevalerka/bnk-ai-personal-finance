import Link from "next/link";
import { Shell } from "@/components/Shell";
import { TradingView } from "@/components/TradingView";
import styles from "@/app/detail.module.css";

export default function TradePage() {
  return (
    <main className={styles.main}>
      <Shell />
      <div className={styles.page}>
        <Link href="/" className={styles.back}>
          ← Back to dashboard
        </Link>

        <header className={styles.header}>
          <span className={styles.title}>Trade</span>
        </header>

        <section className={styles.section}>
          <TradingView />
        </section>
      </div>
    </main>
  );
}
