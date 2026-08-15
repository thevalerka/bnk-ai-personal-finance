import { Fragment } from "react";
import type { FinancialPeriod } from "@/lib/market";
import styles from "./CompanyFinancials.module.css";

function formatUSD(value: number | null): string {
  if (value === null) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatPct(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

function formatEPS(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(2)}`;
}

function periodLabel(period: FinancialPeriod): string {
  const year = new Date(period.period_end).getFullYear();
  if (period.form === "10-K") return `FY${year}`;
  return `${period.fiscal_period} '${String(year).slice(2)}`;
}

interface Row {
  label: string;
  accessor: (p: FinancialPeriod) => number | null;
  format: (v: number | null) => string;
  emphasis?: boolean;
}

interface RowGroup {
  title: string;
  rows: Row[];
}

// Grouped and ordered the way a real income/cash-flow/balance-sheet reads,
// not alphabetically. Real EDGAR data throughout — a null cell renders "—",
// never a fabricated or guessed number (some line items are genuinely
// absent for some companies, e.g. gross margin for a lender — see
// docs/DECISIONS.md ADR-0021/0022).
const ROW_GROUPS: RowGroup[] = [
  {
    title: "Income Statement",
    rows: [
      { label: "Revenue", accessor: (p) => p.revenue, format: formatUSD, emphasis: true },
      { label: "Cost of Revenue", accessor: (p) => p.cost_of_revenue, format: formatUSD },
      { label: "Gross Profit", accessor: (p) => p.gross_profit, format: formatUSD },
      { label: "Gross Margin", accessor: (p) => p.gross_margin_pct, format: formatPct },
      { label: "R&D", accessor: (p) => p.research_development, format: formatUSD },
      { label: "SG&A", accessor: (p) => p.sga_expense, format: formatUSD },
      { label: "Operating Expenses", accessor: (p) => p.operating_expenses, format: formatUSD },
      {
        label: "Operating Income",
        accessor: (p) => p.operating_income,
        format: formatUSD,
        emphasis: true,
      },
      { label: "Operating Margin", accessor: (p) => p.operating_margin_pct, format: formatPct },
      { label: "Interest Expense", accessor: (p) => p.interest_expense, format: formatUSD },
      { label: "Income Tax", accessor: (p) => p.income_tax_expense, format: formatUSD },
      { label: "Net Income", accessor: (p) => p.net_income, format: formatUSD, emphasis: true },
      { label: "Net Margin", accessor: (p) => p.net_margin_pct, format: formatPct },
    ],
  },
  {
    title: "Per Share",
    rows: [
      { label: "EPS (Diluted)", accessor: (p) => p.eps_diluted, format: formatEPS },
      { label: "EPS (Basic)", accessor: (p) => p.eps_basic, format: formatEPS },
    ],
  },
  {
    title: "Cash Flow",
    rows: [
      { label: "Operating Cash Flow", accessor: (p) => p.operating_cash_flow, format: formatUSD },
      { label: "Capital Expenditures", accessor: (p) => p.capex, format: formatUSD },
      {
        label: "Free Cash Flow",
        accessor: (p) => p.free_cash_flow,
        format: formatUSD,
        emphasis: true,
      },
    ],
  },
  {
    title: "Balance Sheet",
    rows: [
      { label: "Total Assets", accessor: (p) => p.total_assets, format: formatUSD },
      { label: "Total Liabilities", accessor: (p) => p.total_liabilities, format: formatUSD },
      { label: "Stockholders' Equity", accessor: (p) => p.stockholders_equity, format: formatUSD },
      { label: "Cash & Equivalents", accessor: (p) => p.cash_and_equivalents, format: formatUSD },
      { label: "Long-Term Debt", accessor: (p) => p.long_term_debt, format: formatUSD },
    ],
  },
];

function FinancialTable({ title, periods }: { title: string; periods: FinancialPeriod[] }) {
  return (
    <div className={styles.tableBlock}>
      <h3 className={styles.tableTitle}>{title}</h3>
      <div className={styles.wrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col" className={styles.metricHeader} />
              {periods.map((period) => (
                <th scope="col" key={period.period_end}>
                  {periodLabel(period)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROW_GROUPS.map((group) => (
              <Fragment key={group.title}>
                <tr className={styles.groupRow}>
                  <th scope="rowgroup" colSpan={periods.length + 1}>
                    {group.title}
                  </th>
                </tr>
                {group.rows.map((row) => (
                  <tr key={row.label}>
                    <th scope="row" className={row.emphasis ? styles.metricEmphasis : styles.metric}>
                      {row.label}
                    </th>
                    {periods.map((period) => {
                      const value = row.accessor(period);
                      return (
                        <td
                          key={period.period_end}
                          className={row.emphasis ? styles.valueEmphasis : styles.value}
                        >
                          {row.format(value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CompanyFinancials({ periods }: { periods: FinancialPeriod[] }) {
  const annual = periods.filter((p) => p.form === "10-K");
  const quarterly = periods.filter((p) => p.form === "10-Q");

  return (
    <div className={styles.sections}>
      {annual.length > 0 ? <FinancialTable title="Annual" periods={annual} /> : null}
      {quarterly.length > 0 ? <FinancialTable title="Quarterly" periods={quarterly} /> : null}
    </div>
  );
}
