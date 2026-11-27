import { LEVEL_COLORS, LEVEL_NAMES } from "../lib/risk";

/** Stacked bar showing what share of the route's miles sit at each risk level. */
export default function RiskBar({ milesByLevel }) {
  const total = milesByLevel.reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="riskbar" role="img" aria-label="Share of route miles by risk level">
      {milesByLevel.map((miles, level) =>
        miles > 0 ? (
          <span
            key={level}
            style={{ width: `${(miles / total) * 100}%`, background: LEVEL_COLORS[level] }}
            title={`${LEVEL_NAMES[level]}: ${Math.round(miles)} mi`}
          />
        ) : null,
      )}
    </div>
  );
}
