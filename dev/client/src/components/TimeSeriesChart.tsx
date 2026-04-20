import { useState, useEffect, useCallback, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { api } from "../lib/api";
import { cn, CARD_SURFACE_B } from "../lib/utils";
import { MenuSelect } from "./MenuSelect";
import { INSTRUMENTED_TAILS, useStore } from "../lib/store";
import type { TimeseriesResponse } from "../lib/types";

const METRICS: { value: string; label: string }[] = [
  { value: "egt_deviation", label: "EGT Deviation" },
  { value: "n1_vibration", label: "N1 Vibration" },
  { value: "oil_temp", label: "Oil Temp" },
  { value: "oil_pressure", label: "Oil Pressure" },
  { value: "fuel_flow", label: "Fuel Flow" },
];

const TAIL_COLORS: Record<string, string> = {
  N287WN: "#ef4444",
  N246WN: "#304cb2",
  N220WN: "#10b981",
  N235WN: "#8b5cf6",
};

const ALL_TAILS = INSTRUMENTED_TAILS as unknown as string[];

/** Always fetch this many datapoints so the dropdown can show the true max. */
const MAX_FETCH = 500;

export default function TimeSeriesChart() {
  const { selectedAircraft } = useStore();
  const defaultTail = selectedAircraft && ALL_TAILS.includes(selectedAircraft) ? selectedAircraft : ALL_TAILS[1];

  const [metric, setMetric] = useState("egt_deviation");
  const [limit, setLimit] = useState(90);
  const [selectedTails, setSelectedTails] = useState<Set<string>>(new Set([defaultTail]));
  const [responseMap, setResponseMap] = useState<Record<string, TimeseriesResponse | null>>({});
  const [loading, setLoading] = useState(false);

  const isOilPressure = metric === "oil_pressure";

  const fetchData = useCallback(() => {
    const tails = [...selectedTails];
    if (tails.length === 0) return;
    setLoading(true);
    if (isOilPressure) {
      const calls: Array<Promise<TimeseriesResponse | null>> = [];
      const keys: string[] = [];
      for (const t of tails) {
        calls.push(api.timeseries(t, "oil_pressure_min", MAX_FETCH).catch(() => null));
        calls.push(api.timeseries(t, "oil_pressure_max", MAX_FETCH).catch(() => null));
        keys.push(`${t}_min`, `${t}_max`);
      }
      Promise.all(calls)
        .then((results) => {
          const map: Record<string, TimeseriesResponse | null> = {};
          keys.forEach((k, i) => { map[k] = results[i]; });
          setResponseMap(map);
        })
        .finally(() => setLoading(false));
    } else {
      Promise.all(tails.map((t) => api.timeseries(t, metric, MAX_FETCH).catch(() => null)))
        .then((results) => {
          const map: Record<string, TimeseriesResponse | null> = {};
          tails.forEach((t, i) => { map[t] = results[i]; });
          setResponseMap(map);
        })
        .finally(() => setLoading(false));
    }
  }, [metric, selectedTails, isOilPressure]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleTail = (tail: string) => {
    setSelectedTails((prev) => {
      const next = new Set(prev);
      if (next.has(tail)) { if (next.size > 1) next.delete(tail); }
      else next.add(tail);
      return next;
    });
  };

  // True max available datapoints across all selected aircraft (from MAX_FETCH responses).
  const maxDatapoints = useMemo(() => {
    let m = 0;
    for (const resp of Object.values(responseMap)) {
      if (resp && resp.datapoints.length > m) m = resp.datapoints.length;
    }
    return m || 10;
  }, [responseMap]);

  // Clamp limit to actual available max.
  useEffect(() => {
    if (maxDatapoints > 0 && limit > maxDatapoints) setLimit(maxDatapoints);
  }, [maxDatapoints]);

  const limitOptions = useMemo(() => {
    const maxStep = Math.ceil(maxDatapoints / 10) * 10;
    const opts: { value: string; label: string }[] = [];
    for (let n = 10; n <= maxStep; n += 10) {
      opts.push({ value: String(n), label: `${n} flights` });
    }
    return opts;
  }, [maxDatapoints]);

  const chartData = useMemo(() => {
    if (isOilPressure) {
      const byTail: Record<string, { min: (number | null)[]; max: (number | null)[] }> = {};
      let maxLen = 0;
      for (const tail of selectedTails) {
        const minResp = responseMap[`${tail}_min`];
        const maxResp = responseMap[`${tail}_max`];
        const len = Math.max(minResp?.datapoints.length ?? 0, maxResp?.datapoints.length ?? 0);
        if (len > maxLen) maxLen = len;
        byTail[tail] = {
          min: (minResp?.datapoints ?? []).map((d) => d.value),
          max: (maxResp?.datapoints ?? []).map((d) => d.value),
        };
      }
      const showCount = Math.min(maxLen, limit);
      // Build entries indexed by flights ago (0 = most recent, higher = older).
      // Align each aircraft's newest datapoint to idx=0 (right side of chart).
      const rows = Array.from({ length: showCount }, (_, flightsAgo) => {
        const entry: Record<string, unknown> = { idx: flightsAgo };
        for (const [tail, { min, max }] of Object.entries(byTail)) {
          const minIdx = min.length - 1 - flightsAgo;
          const maxIdx = max.length - 1 - flightsAgo;
          let lo = minIdx >= 0 ? (min[minIdx] ?? null) : null;
          let hi = maxIdx >= 0 ? (max[maxIdx] ?? null) : null;
          if (lo !== null && hi !== null && lo > hi) { [lo, hi] = [hi, lo]; }
          entry[`${tail}_min`] = lo;
          entry[`${tail}_max`] = hi;
        }
        return entry;
      });
      // Reverse so array goes [showCount-1, ..., 1, 0] — left=oldest, right=0=newest.
      rows.sort((a, b) => (b.idx as number) - (a.idx as number));
      return rows;
    }

    const byTail: Record<string, (number | null)[]> = {};
    let maxLen = 0;
    for (const [tail, resp] of Object.entries(responseMap)) {
      if (!resp || resp.datapoints.length === 0) continue;
      const pts = resp.datapoints.map((dp) => dp.value);
      byTail[tail] = pts;
      if (pts.length > maxLen) maxLen = pts.length;
    }
    const showCount = Math.min(maxLen, limit);
    const rows = Array.from({ length: showCount }, (_, flightsAgo) => {
      const entry: Record<string, unknown> = { idx: flightsAgo };
      for (const [tail, pts] of Object.entries(byTail)) {
        const ptsIdx = pts.length - 1 - flightsAgo;
        entry[tail] = ptsIdx >= 0 ? (pts[ptsIdx] ?? null) : null;
      }
      return entry;
    });
    rows.sort((a, b) => (b.idx as number) - (a.idx as number));
    return rows;
  }, [responseMap, selectedTails, isOilPressure, limit]);

  // Stats from visible data
  const { statsMin, statsMax, statsAvg } = useMemo(() => {
    const allVals: number[] = [];
    for (const row of chartData) {
      for (const [k, v] of Object.entries(row)) {
        if (k !== "idx" && typeof v === "number" && !Number.isNaN(v)) allVals.push(v);
      }
    }
    if (allVals.length === 0) return { statsMin: null, statsMax: null, statsAvg: null };
    const mn = Math.min(...allVals);
    const mx = Math.max(...allVals);
    const avg = allVals.reduce((s, v) => s + v, 0) / allVals.length;
    return { statsMin: mn, statsMax: mx, statsAvg: avg };
  }, [chartData]);

  const firstResp = Object.values(responseMap).find(Boolean);
  const cautionThreshold = firstResp?.caution_threshold ?? null;
  const criticalThreshold = firstResp?.critical_threshold ?? null;
  const unit = firstResp?.unit ?? "";

  // Extend Y-axis max to include threshold lines so they're always visible.
  const domainMax = useMemo(() => {
    const threshMax = criticalThreshold ?? cautionThreshold ?? null;
    if (statsMax !== null && threshMax !== null) {
      return Math.ceil(Math.max(statsMax, threshMax) * 1.12);
    }
    if (threshMax !== null) return Math.ceil(threshMax * 1.2);
    return "auto" as const;
  }, [criticalThreshold, cautionThreshold, statsMax]);

  const fmtVal = (v: number) => Math.abs(v) < 100 ? v.toFixed(2) : v.toFixed(0);

  return (
    <div className={cn("rounded-b-xl p-4 flex flex-col gap-3", CARD_SURFACE_B)}>
      {/* Controls row */}
      <div className="flex items-center gap-3 flex-wrap shrink-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          {ALL_TAILS.map((tail) => (
            <button
              key={tail}
              type="button"
              onClick={() => toggleTail(tail)}
              className={cn(
                "px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors",
                selectedTails.has(tail)
                  ? "text-white border-transparent"
                  : "bg-slate-100 text-slate-500 border-slate-200 hover:border-slate-400"
              )}
              style={selectedTails.has(tail) ? { backgroundColor: TAIL_COLORS[tail], borderColor: TAIL_COLORS[tail] } : {}}
            >
              {tail}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap ml-auto">
          <MenuSelect value={metric} options={METRICS} onChange={(v) => { setMetric(v); }} ariaLabel="Select metric" />
          <MenuSelect
            value={String(limit)}
            options={limitOptions.length ? limitOptions : [{ value: String(limit), label: `${limit} flights` }]}
            onChange={(v) => setLimit(Number(v))}
            ariaLabel="Select flight count"
          />
        </div>
      </div>

      {/* Stats bar */}
      {statsMin !== null && (
        <div className="flex gap-4 text-xs text-slate-500 shrink-0">
          <span>Min: <span className="font-medium text-slate-700">{fmtVal(statsMin)}{unit ? " " + unit : ""}</span></span>
          <span>Max: <span className="font-medium text-slate-700">{fmtVal(statsMax!)}{unit ? " " + unit : ""}</span></span>
          <span>Avg: <span className="font-medium text-slate-700">{fmtVal(statsAvg!)}{unit ? " " + unit : ""}</span></span>
        </div>
      )}

      {/* Chart */}
      <div className="h-52 w-full">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <span className="text-xs text-slate-400 animate-pulse">Loading…</span>
          </div>
        ) : chartData.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <span className="text-xs text-slate-400">No data for selected aircraft and metric</span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="idx"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickLine={false}
                axisLine={{ stroke: "#e2e8f0" }}
                label={{ value: "flights ago →", position: "insideBottomRight", offset: -4, fontSize: 10, fill: "#94a3b8" }}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickLine={false}
                axisLine={false}
                unit={unit ? ` ${unit}` : ""}
                width={58}
                domain={["auto", domainMax]}
              />
              <Tooltip
                contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0", backgroundColor: "white" }}
                formatter={(value: unknown) =>
                  value !== null && value !== undefined
                    ? [`${(value as number).toFixed(2)}${unit ? " " + unit : ""}`]
                    : ["—"]
                }
                labelFormatter={(label) => `${label} flight${Number(label) === 1 ? "" : "s"} ago`}
              />
              <Legend iconType="line" iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              {cautionThreshold !== null && (
                <ReferenceLine
                  y={cautionThreshold}
                  stroke="#f97316"
                  strokeDasharray="4 4"
                  label={{ value: "Caution", position: "insideTopRight", fontSize: 10, fill: "#ea580c" }}
                />
              )}
              {criticalThreshold !== null && (
                <ReferenceLine
                  y={criticalThreshold}
                  stroke="#ef4444"
                  strokeDasharray="4 4"
                  label={{ value: "Critical", position: "insideTopRight", fontSize: 10, fill: "#dc2626" }}
                />
              )}
              {isOilPressure
                ? [...selectedTails].flatMap((tail) => [
                    <Line
                      key={`${tail}_min`}
                      type="monotone"
                      dataKey={`${tail}_min`}
                      stroke={TAIL_COLORS[tail] ?? "#94a3b8"}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      name={`${tail} min`}
                    />,
                    <Line
                      key={`${tail}_max`}
                      type="monotone"
                      dataKey={`${tail}_max`}
                      stroke={TAIL_COLORS[tail] ?? "#94a3b8"}
                      strokeWidth={1.5}
                      strokeOpacity={0.5}
                      dot={false}
                      connectNulls
                      name={`${tail} max`}
                    />,
                  ])
                : [...selectedTails].map((tail) => (
                    <Line
                      key={tail}
                      type="monotone"
                      dataKey={tail}
                      stroke={TAIL_COLORS[tail] ?? "#94a3b8"}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      name={tail}
                    />
                  ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
