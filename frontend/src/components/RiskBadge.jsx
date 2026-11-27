import { LEVEL_COLORS, LEVEL_NAMES } from "../lib/risk";

export default function RiskBadge({ level }) {
  return (
    <span className="badge" style={{ background: LEVEL_COLORS[level], color: level === 1 ? "#222" : "#fff" }}>
      {LEVEL_NAMES[level]}
    </span>
  );
}
