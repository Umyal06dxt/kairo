/** "B1 Lost debit card" -> "Lost debit card" (the code prefix is for ordering, not for people). */
export const scenarioLabel = (key: string): string => key.replace(/^[A-Za-z]{1,2}\d+\s+/, "");

/** "Harbor FCU - credit union voice support" -> "Credit union voice support". */
export function shortDomain(title: string): string {
  const t = title.includes(" - ") ? title.split(" - ").slice(1).join(" - ") : title;
  return t.charAt(0).toUpperCase() + t.slice(1);
}
