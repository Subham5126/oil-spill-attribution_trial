export function parseUtcMs(value?: string | number | null): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  let s = String(value).trim().replace(" ", "T");
  // If string does not contain an explicit timezone indicator (Z, +HH:MM, -HH:MM), append Z
  if (!s.endsWith("Z") && !/[+-]\d{2}(?::?\d{2})?$/.test(s)) {
    s += "Z";
  }
  const parsed = Date.parse(s);
  return Number.isNaN(parsed) ? null : parsed;
}

export function formatInvestigationUtc(ms: number): { clock: string; full: string } {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) {
    return { clock: "—", full: "Timestamp unavailable" };
  }
  const yyyy = d.getUTCFullYear();
  const mon = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  const ss = String(d.getUTCSeconds()).padStart(2, "0");
  return {
    clock: `${hh}:${mm}:${ss} UTC`,
    full: `${dd} ${mon} ${yyyy} • ${hh}:${mm}:${ss} UTC`,
  };
}

export function clampTime(t: number, start: number, end: number): number {
  if (!Number.isFinite(t)) return start;
  if (end <= start) return start;
  return Math.min(end, Math.max(start, t));
}
