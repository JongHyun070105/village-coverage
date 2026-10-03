/** Public-sector display formats: ₩4,608,959 and 2026. 10. 03. */
export function won(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "미정";
  return `₩${Math.round(amount).toLocaleString("ko-KR")}`;
}

export function koreanDate(value: string | null | undefined): string {
  if (!value) return "-";
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return `${year}. ${month}. ${day}.`;
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "-";
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: digits })}%`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("ko-KR");
}
