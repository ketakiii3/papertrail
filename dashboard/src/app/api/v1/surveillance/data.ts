// Sample event-study results for demo mode. Insider names are placeholders,
// not real people; numbers are illustrative.

type DailyAR = { date: string; ret: number; expected: number; ar: number };

function dailyAR(start: string, ars: number[], marketRets: number[], beta: number): DailyAR[] {
  const d0 = new Date(start + "T00:00:00Z");
  return ars.map((ar, i) => {
    const d = new Date(d0);
    d.setUTCDate(d0.getUTCDate() + i);
    const expected = 0.0004 + beta * marketRets[i];
    return { date: d.toISOString().slice(0, 10), ret: expected + ar, expected, ar };
  });
}

const base = [
  {
    id: 1, transaction_id: 101, ticker: "AAPL", company_name: "Apple Inc.",
    insider_name: "Sample Insider A", insider_title: "Chief Operating Officer",
    transaction_type: "sell", transaction_date: "2025-04-04",
    shares: 50000, price: 188.38, total_value: 9_419_000,
    event_date: "2025-04-04", car: 0.0871, car_zscore: 2.71, volume_ratio: 2.31,
    flagged: true, flag_reason: "abnormal_return_and_volume",
    baseline_alpha: 0.0007, baseline_beta: 1.04, baseline_r2: 0.56,
    daily_ar: dailyAR("2025-04-04", [0.021, 0.018, 0.016, 0.012, 0.011, 0.009], [-0.05, 0.01, -0.02, 0.09, -0.03, 0.02], 1.04),
  },
  {
    id: 2, transaction_id: 102, ticker: "MSFT", company_name: "Microsoft Corporation",
    insider_name: "Sample Insider B", insider_title: "Director",
    transaction_type: "buy", transaction_date: "2025-02-12",
    shares: 2500, price: 409.04, total_value: 1_022_600,
    event_date: "2025-02-12", car: 0.0124, car_zscore: 0.88, volume_ratio: 1.12,
    flagged: false, flag_reason: "below_threshold",
    baseline_alpha: 0.0003, baseline_beta: 0.97, baseline_r2: 0.61,
    daily_ar: dailyAR("2025-02-12", [0.004, 0.002, -0.001, 0.003, 0.002, 0.002], [0.003, -0.004, 0.006, 0.001, -0.002, 0.004], 0.97),
  },
  {
    id: 3, transaction_id: 103, ticker: "TSLA", company_name: "Tesla Inc.",
    insider_name: "Sample Insider C", insider_title: "Chief Financial Officer",
    transaction_type: "sell", transaction_date: "2025-07-28",
    shares: 12000, price: 321.2, total_value: 3_854_400,
    event_date: "2025-07-28", car: -0.0412, car_zscore: -1.35, volume_ratio: 1.78,
    flagged: false, flag_reason: "below_threshold",
    baseline_alpha: 0.0011, baseline_beta: 1.82, baseline_r2: 0.38,
    daily_ar: dailyAR("2025-07-28", [-0.011, -0.009, -0.006, -0.008, -0.004, -0.003], [0.002, -0.006, 0.004, -0.001, 0.003, 0.001], 1.82),
  },
];

export const surveillanceFlags = base.map((f) => ({ ...f, computed_at: "2025-10-01T00:00:00Z" }));
