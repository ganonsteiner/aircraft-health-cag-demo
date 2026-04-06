import type { FlightRecord } from "./types";

/** Cylinder head temp caution (demo band). */
export const CHT_HIGH_F = 420;
/** Oil temp caution (demo band). */
export const OIL_TEMP_HIGH_F = 215;
/** EGT caution for piston cruise context (demo). */
export const EGT_HIGH_F = 1350;
/** Oil pressure low caution (psi). */
export const OIL_PSI_MIN_LOW = 55;
/** Oil pressure high caution (psi). */
export const OIL_PSI_MAX_HIGH = 85;

export function isChtHigh(v: number | null | undefined): boolean {
  return v !== null && v !== undefined && v >= CHT_HIGH_F;
}

export function isOilTempHigh(v: number | null | undefined): boolean {
  return v !== null && v !== undefined && v >= OIL_TEMP_HIGH_F;
}

export function isEgtHigh(v: number | null | undefined): boolean {
  return v !== null && v !== undefined && v >= EGT_HIGH_F;
}

export function isOilPsiMinLow(v: number | null | undefined): boolean {
  return v !== null && v !== undefined && v <= OIL_PSI_MIN_LOW;
}

export function isOilPsiMaxHigh(v: number | null | undefined): boolean {
  return v !== null && v !== undefined && v >= OIL_PSI_MAX_HIGH;
}

export type TelemetrySortField =
  | "cht_max"
  | "oil_temp_max"
  | "oil_pressure_min"
  | "oil_pressure_max"
  | "egt_max"
  | "fuel_used_gal";

/** True if sort-preview / row styling should warn for this field and record (never fuel). */
export function telemetrySortFieldIsWarn(field: TelemetrySortField, rec: FlightRecord): boolean {
  if (field === "fuel_used_gal") return false;
  switch (field) {
    case "cht_max":
      return isChtHigh(rec.cht_max);
    case "oil_temp_max":
      return isOilTempHigh(rec.oil_temp_max);
    case "oil_pressure_min":
      return isOilPsiMinLow(rec.oil_pressure_min);
    case "oil_pressure_max":
      return isOilPsiMaxHigh(rec.oil_pressure_max);
    case "egt_max":
      return isEgtHigh(rec.egt_max);
    default:
      return false;
  }
}
