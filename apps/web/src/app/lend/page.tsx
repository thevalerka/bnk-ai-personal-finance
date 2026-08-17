import Link from "next/link";
import { Shell } from "@/components/Shell";
import { LendView } from "@/components/LendView";
import styles from "@/app/detail.module.css";

export default function LendPage() {
  return (
    <main className={styles.main}>
      <Shell />
      <div className={styles.page}>
        <Link href="/" className={styles.back}>
          ← Back to dashboard
        </Link>

        <header className={styles.header}>
          <span className={styles.title}>Fixed Income — Stablecoin Lending</span>
        </header>

        <section className={styles.section}>
          <LendView />
        </section>
      </div>
    </main>
  );
}
