import Link from "next/link";
import { Shell } from "@/components/Shell";
import { XStocksView } from "@/components/XStocksView";
import styles from "@/app/detail.module.css";

export default function XStocksPage() {
  return (
    <main className={styles.main}>
      <Shell />
      <div className={styles.page}>
        <Link href="/" className={styles.back}>
          ← Back to dashboard
        </Link>

        <header className={styles.header}>
          <span className={styles.title}>xStocks</span>
        </header>

        <section className={styles.section}>
          <XStocksView />
        </section>
      </div>
    </main>
  );
}
