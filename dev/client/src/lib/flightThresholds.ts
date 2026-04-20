import type { FlightRecord } from "./types";

/** CFM56-7B EGT deviation caution threshold (°C above baseline). */
export const EGT_DEV_CAUTION = 10;
/** CFM56-7B EGT deviation warning threshold (°C above baseline). */
export const EGT_DEV_WARNING = 15;
/** N1 vibration caution threshold (units). */
export const N1_VIB_CAUTION = 1.8;
/** N1 vibration warning threshold (units). */
export const N1_VIB_WARNING = 2.5;
/** Oil temp max caution (°C). */
export const OIL_TEMP_CAUTION_C = 102;
/** Oil temp max warning (°C). */
export const OIL_TEMP_WARNING_C = 110;
/** Oil pressure min caution low (psi). */
export const OIL_PSI_MIN_CAUTION = 40;
/** Oil pressure min dangerous low (psi). */
export const OIL_PSI_MIN_DANGEROUS = 30;
/** Oil pressure max caution high (psi). */
export const OIL_PSI_MAX_CAUTION = 80;
/** Oil pressure max dangerous high (psi). */
export const OIL_PSI_MAX_DANGEROUS = 90;

export type TelemetrySeverity = "ok" | "warn" | "bad";

export type TelemetrySortField =
  | "egt_deviation"
  | "n1_vibration"
  | "oil_temp_max"
  | "oil_pressure_min"
  | "oil_pressure_max"
  | "fuel_flow_kgh";

export function telemetrySeverityForField(field: TelemetrySortField, rec: FlightRecord): TelemetrySeverity {
  switch (field) {
    case "egt_deviation":
      if (rec.egt_deviation === null) return "ok";
      if (rec.egt_deviation >= EGT_DEV_WARNING) return "bad";
      if (rec.egt_deviation >= EGT_DEV_CAUTION) return "warn";
      return "ok";
    case "n1_vibration":
      if (rec.n1_vibration === null) return "ok";
      if (rec.n1_vibration >= N1_VIB_WARNING) return "bad";
      if (rec.n1_vibration >= N1_VIB_CAUTION) return "warn";
      return "ok";
    case "oil_temp_max":
      if (rec.oil_temp_max === null) return "ok";
      if (rec.oil_temp_max >= OIL_TEMP_WARNING_C) return "bad";
      if (rec.oil_temp_max >= OIL_TEMP_CAUTION_C) return "warn";
      return "ok";
    case "oil_pressure_min":
      if (rec.oil_pressure_min === null) return "ok";
      if (rec.oil_pressure_min <= OIL_PSI_MIN_DANGEROUS) return "bad";
      if (rec.oil_pressure_min <= OIL_PSI_MIN_CAUTION) return "warn";
      return "ok";
    case "oil_pressure_max":
      if (rec.oil_pressure_max === null) return "ok";
      if (rec.oil_pressure_max >= OIL_PSI_MAX_DANGEROUS) return "bad";
      if (rec.oil_pressure_max >= OIL_PSI_MAX_CAUTION) return "warn";
      return "ok";
    case "fuel_flow_kgh":
      return "ok";
    default:
      return "ok";
  }
}

export function telemetrySortFieldIsWarn(field: TelemetrySortField, rec: FlightRecord): boolean {
  return telemetrySeverityForField(field, rec) !== "ok";
}
