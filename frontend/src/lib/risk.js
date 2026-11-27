export const LEVEL_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"];
export const LEVEL_COLORS = ["#2e9e5b", "#e3c21f", "#f08a24", "#d7301f", "#6a1b9a"];
export const ROUTE_COLORS = ["#1d6fe0", "#7c3aed", "#0f9e9e"];

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const RGB = LEVEL_COLORS.map(rgb);

/** Smoothly blends the level colours for a fractional score between 0 and 4. */
export function scoreColor(score) {
  const s = Math.max(0, Math.min(4, score));
  const i = Math.min(3, Math.floor(s));
  const t = s - i;
  const c = RGB[i].map((v, k) => Math.round(v + (RGB[i + 1][k] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
