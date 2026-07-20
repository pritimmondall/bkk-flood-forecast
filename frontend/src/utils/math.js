/**
 * math.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Pure helper functions for numerical operations used across the dashboard.
 * All functions are side-effect-free and fully typed.
 * ─────────────────────────────────────────────────────────────────────────────
 */

/** Clamp a value between min and max (inclusive) */
export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/** Linear interpolation between start and end at position t ∈ [0, 1] */
export function lerp(start, end, t) {
  return start + (end - start) * clamp(t, 0, 1);
}

/** Map a value from one range to another */
export function mapRange(value, inMin, inMax, outMin, outMax) {
  const t = (value - inMin) / (inMax - inMin);
  return lerp(outMin, outMax, t);
}

/** Round to a given number of decimal places */
export function roundTo(value, decimals) {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}

/** Calculate percentage of value relative to total */
export function pct(value, total) {
  if (total === 0) return 0;
  return roundTo(value / total * 100, 1);
}

/** Format a number with a thousands-separator for display (e.g. 1140 → "1,140") */
export function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

/** Determine severity colour hex from a 0–100 risk score */
export function riskScoreToColor(score) {
  if (score >= 80) return "#ef4444"; // critical
  if (score >= 60) return "#f97316"; // warning
  if (score >= 40) return "#eab308"; // watch
  return "#22c55e"; // normal
}