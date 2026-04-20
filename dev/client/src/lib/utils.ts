import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Airworthiness } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type Tone = "ok" | "warn" | "bad" | "unknown";

export type ToneClasses = {
  tone: Tone;
  text: string;
  /** Tier B semantic tint — content card with hue wash. Same luminance as CARD_SURFACE_B. */
  panel: string;
  /** Tier B semantic tint with left accent — for banner/hero cards (airworthiness, error alerts). */
  bannerPanel: string;
  /** Border-only variant for subtle outlines. */
  border: string;
  /** Pill/badge chip. */
  badge: string;
  /** Small dot indicator. */
  dot: string;
};

// ---------------------------------------------------------------------------
// Surface tier tokens
// ---------------------------------------------------------------------------

/** 1px stroke — identical for Tier A and Tier B; only fill differs.
 *  Uses the themed --border token (cooler/darker than slate-200) so edges read
 *  cleanly against both canvas and card fills. */
const CARD_SURFACE_OUTLINE = "border border-border";

/** Tier A — layout shell (one step up from the page canvas).
 *  Uses `bg-muted` so a shell is always visibly distinct from the page, never
 *  a perfect color match. For transparent-looking layout frames and shells
 *  that wrap Tier B content. */
export const CARD_SURFACE_A = `${CARD_SURFACE_OUTLINE} bg-muted`;

/** Tier B — content card / subject. The readable unit. Standalone cards and
 *  items inside a Tier A container both use this surface. */
export const CARD_SURFACE_B = `${CARD_SURFACE_OUTLINE} bg-card`;

/**
 * Tab page body: same max width as header/tab bar, symmetric horizontal padding so the column
 * stays centered in the viewport. (Floating chat FAB is fixed; do not offset layout with asymmetric padding.)
 */
export const MAIN_TAB_CONTENT_FRAME =
  "max-w-screen-2xl mx-auto w-full min-w-0 px-4 sm:px-6";

/**
 * Top padding from the app tab bar to the first content row — matches Hangar (FleetPage).
 * Use with MAIN_TAB_CONTENT_FRAME; pair with pb-* for bottom inset (e.g. pb-6).
 */
export const TAB_PAGE_TOP_INSET = "pt-3 sm:pt-4";

/**
 * Narrower column for tab pages whose main content is capped at ~56rem (e.g. Aircraft Status,
 * Maintenance). Use for tail selectors so they align with cards below the fold.
 */
export const TAB_PAGE_READABLE_COLUMN = "max-w-4xl mx-auto w-full min-w-0";

/** Tier C — inline chip / metric, nested inside a Tier B card. */
export const CARD_SURFACE_C = "border border-border bg-muted";

/** @deprecated Use CARD_SURFACE_C */
export const NEUTRAL_METRIC_SURFACE = CARD_SURFACE_C;

/** @deprecated Use CARD_SURFACE_B */
export const NEUTRAL_CARD_SURFACE = CARD_SURFACE_B;

// Tone palette: card-sized surfaces (panel, bannerPanel) stay visually quiet
// on the light app background — no tinted fills, only colored text + border
// accents. Small semantic pills (badge) keep a subtle tint because they're
// inline markers, not full cards.
// Design rule: cards WITHOUT a left accent keep neutral borders (CARD_SURFACE_B).
// Cards WITH a left accent get a thin colored border on ALL four sides so the
// accent looks intentional rather than isolated. Use *-300 for the thin sides
// (clearly visible as colored, unlike nearly-invisible *-200) and *-500 for
// the 3px left accent. Side-specific utilities win over the global
// `* { border-color: var(--border) }` reset in index.css.
const TONE_CLASS: Record<Tone, Omit<ToneClasses, "tone">> = {
  ok: {
    text: "text-emerald-700",
    panel: CARD_SURFACE_B,
    bannerPanel: "border border-emerald-300 bg-card border-l-[3px] border-l-emerald-500",
    border: "border-slate-200",
    badge: "text-emerald-700 bg-emerald-50 border-emerald-200",
    dot: "bg-emerald-500",
  },
  warn: {
    text: "text-orange-700",
    panel: CARD_SURFACE_B,
    bannerPanel: "border border-orange-300 bg-card border-l-[3px] border-l-orange-500",
    border: "border-slate-200",
    badge: "text-orange-700 bg-orange-50 border-orange-200",
    dot: "bg-orange-500",
  },
  bad: {
    text: "text-red-700",
    panel: CARD_SURFACE_B,
    bannerPanel: "border border-red-300 bg-card border-l-[3px] border-l-red-500",
    border: "border-slate-200",
    badge: "text-red-700 bg-red-50 border-red-200",
    dot: "bg-red-500",
  },
  unknown: {
    text: "text-slate-500",
    panel: CARD_SURFACE_B,
    bannerPanel: `border border-slate-300 bg-card border-l-[3px] border-l-slate-400`,
    border: "border-slate-200",
    badge: "text-slate-500 bg-slate-50 border-slate-200",
    dot: "bg-slate-400",
  },
};

/** Color shared with the Knowledge Graph document node. Changing either updates both. */
export const KG_DOCUMENT_NODE_COLOR = "text-purple-500";
export const AD_ACCENT_TEXT = KG_DOCUMENT_NODE_COLOR;

export function toneClasses(tone: Tone): ToneClasses {
  return { tone, ...TONE_CLASS[tone] };
}

export function toneForDue(value: number | null, unit: "hours" | "days"): ToneClasses {
  if (value === null) return toneClasses("unknown");
  if (value < 0) return toneClasses("bad");
  const warnThreshold = unit === "hours" ? 5 : 30;
  if (value <= warnThreshold) return toneClasses("warn");
  return toneClasses("ok");
}

export type OilLifeToneInput = {
  /** Positive number of tach-hours overdue (0 if not overdue/unknown). */
  oilHoursOverdue: number;
  /** Tach-hours remaining until due (negative if overdue, 0 if due now). */
  oilTachHoursUntilDue: number;
  /** Calendar days remaining until due (negative if overdue), or null if unknown/not tracked. */
  oilDaysUntilDue: number | null;
};

/**
 * Oil Life coloring aligned with backend ferry policy:
 * - Red only when non-ferryable (tach overdue > 5.0 OR calendar overdue >= 14 days)
 * - Yellow when almost due OR overdue-but-still-ferryable
 */
export function toneForOilLife(input: OilLifeToneInput): ToneClasses {
  const { oilHoursOverdue, oilTachHoursUntilDue, oilDaysUntilDue } = input;

  const safeHoursOverdue = Number.isFinite(oilHoursOverdue) ? Math.max(0, oilHoursOverdue) : 0;
  const calendarOverdueDays =
    oilDaysUntilDue !== null && Number.isFinite(oilDaysUntilDue) && oilDaysUntilDue < 0
      ? Math.abs(oilDaysUntilDue)
      : 0;

  // Non-ferryable thresholds (must match backend: tach > 5, calendar >= 14)
  if (safeHoursOverdue > 5.0 || calendarOverdueDays >= 14) return toneClasses("bad");

  const hasAnySignal =
    safeHoursOverdue > 0 ||
    calendarOverdueDays > 0 ||
    Number.isFinite(oilTachHoursUntilDue) ||
    (oilDaysUntilDue !== null && Number.isFinite(oilDaysUntilDue));

  if (!hasAnySignal) return toneClasses("unknown");

  const almostDueTach =
    Number.isFinite(oilTachHoursUntilDue) && oilTachHoursUntilDue > 0 && oilTachHoursUntilDue <= 5;
  const almostDueCalendar =
    oilDaysUntilDue !== null && Number.isFinite(oilDaysUntilDue) && oilDaysUntilDue >= 0 && oilDaysUntilDue <= 30;

  // Ferry-able overdue OR almost due
  if (safeHoursOverdue > 0 || calendarOverdueDays >= 1 || almostDueTach || almostDueCalendar) {
    return toneClasses("warn");
  }

  return toneClasses("ok");
}

/**
 * Compact tach-hours for oil-life UI: one decimal when the integer part of |h| is under 10;
 * otherwise nearest whole hour (keeps narrow tiles on one row).
 */
export function formatSignedOilHoursCompact(
  h: number,
  unitSeparator: " " | "\u00a0" = "\u00a0"
): string {
  const abs = Math.abs(h);
  const sign = h < 0 ? "-" : "";
  const intPart = Math.floor(abs);
  const valueStr = intPart >= 10 ? String(Math.round(abs)) : abs.toFixed(1);
  return `${sign}${valueStr}${unitSeparator}hr`;
}

export function toneForAirworthiness(a: Airworthiness | null | undefined): ToneClasses {
  switch (a) {
    case "AIRWORTHY":
      return toneClasses("ok");
    case "FERRY_ONLY":
    case "CAUTION":
      return toneClasses("warn");
    case "NOT_AIRWORTHY":
      return toneClasses("bad");
    case "UNKNOWN":
    default:
      return toneClasses("unknown");
  }
}

export function toneForSquawks(openCount: number, groundingCount: number): ToneClasses {
  if (groundingCount > 0) return toneClasses("bad");
  if (openCount > 0) return toneClasses("warn");
  return toneClasses("ok");
}

/**
 * Calendar dates from the API are ISO `YYYY-MM-DD` (no time zone). `new Date("YYYY-MM-DD")`
 * is specified as UTC midnight, which shifts to the previous local calendar day west of UTC;
 * we interpret date-only strings as local civil dates instead.
 */
function parseDateInput(dateStr: string): Date {
  const trimmed = dateStr.trim();
  const cal = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (cal) {
    const y = Number(cal[1]);
    const mo = Number(cal[2]) - 1;
    const d = Number(cal[3]);
    return new Date(y, mo, d);
  }
  return new Date(trimmed);
}

/**
 * Whole calendar days from local today to a date-only ISO string (negative = past / overdue).
 * Matches API day counts from calendar_days_until_iso when browser and server share local TZ.
 */
export function calendarDaysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr?.trim()) return null;
  const target = parseDateInput(dateStr);
  if (isNaN(target.getTime())) return null;
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startTarget = new Date(
    target.getFullYear(),
    target.getMonth(),
    target.getDate()
  ).getTime();
  return Math.round((startTarget - startToday) / 86400000);
}

export function formatDate(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const d = parseDateInput(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

/** Numeric local date for compact UI: MM/DD/YY (two digits each). */
export function formatDateMMDDYY(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const d = parseDateInput(dateStr);
  if (isNaN(d.getTime())) return null;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yy = String(d.getFullYear() % 100).padStart(2, "0");
  return `${mm}/${dd}/${yy}`;
}

/** Same as MM/DD/YY but with hyphens — pairs with slash dividers elsewhere without visual clash. */
export function formatDateMMDDYYHyphen(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const d = parseDateInput(dateStr);
  if (isNaN(d.getTime())) return null;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yy = String(d.getFullYear() % 100).padStart(2, "0");
  return `${mm}-${dd}-${yy}`;
}

export function formatTimestamp(ts: number | null | undefined): string {
  if (!ts) return "Unknown";
  return new Date(ts).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function urgencyColor(daysOrHours: number | null, type: "days" | "hours"): string {
  return toneForDue(daysOrHours, type === "hours" ? "hours" : "days").text;
}

/** Human-readable maintenance subtype for badges (e.g. oil_change → Oil change). */
export function formatMaintenanceTypeLabel(raw: string): string {
  const t = (raw || "").trim().toLowerCase().replace(/ /g, "_");
  const map: Record<string, string> = {
    oil_change: "Oil change",
    annual: "Annual inspection",
    "100hr": "100-hour inspection",
    progressive: "Progressive inspection",
    squawk: "Squawk",
    post_accident_inspection: "Post-accident inspection",
  };
  return map[t] || raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Maintenance";
}

/** Avoid "AD AD 80-04-03" when metadata already includes the AD prefix. */
export function formatAdReferenceLine(ref: string): string {
  const t = ref.trim();
  if (!t) return "";
  if (/^ad\s/i.test(t)) return t;
  return `AD ${t}`;
}

/** Squawk/symptom row: Tier B card with severity left accent.
 *  Accented rows get a thin matching border on all four sides so the accent
 *  reads as intentional. Cosmetic/neutral rows keep the default neutral border. */
export function severityRowClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case "grounding":
    case "critical":
      return `${CARD_SURFACE_B} rounded-lg border-red-300 border-l-[3px] border-l-red-500 text-slate-800`;
    case "non-grounding":
    case "caution":
    case "warning":
      return `${CARD_SURFACE_B} rounded-lg border-orange-300 border-l-[3px] border-l-orange-500 text-slate-800`;
    case "cosmetic":
      return `${CARD_SURFACE_B} rounded-lg border-l-[3px] border-l-slate-300 text-slate-700`;
    default:
      return `${CARD_SURFACE_B} rounded-lg border-l-[3px] border-l-slate-300 text-slate-700`;
  }
}

/** Small severity pill on squawk/symptom rows (keeps hue in the label). */
export function severityPillClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case "grounding":
      return "text-red-700 bg-red-50 border-red-200";
    case "non-grounding":
      return "text-orange-700 bg-orange-50 border-orange-200";
    case "cosmetic":
      return "text-slate-500 bg-slate-50 border-slate-200";
    case "caution":
    case "warning":
      return "text-orange-700 bg-orange-50 border-orange-200";
    case "critical":
      return "text-red-700 bg-red-50 border-red-200";
    default:
      return "text-slate-500 bg-slate-50 border-slate-200";
  }
}
