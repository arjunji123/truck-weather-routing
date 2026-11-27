import { formatDateTime, formatDuration, formatMiles } from "../lib/format";
import { ROUTE_COLORS } from "../lib/risk";
import RiskBadge from "./RiskBadge";
import RiskBar from "./RiskBar";

export default function RouteCard({ route, index, selected, recommended, onSelect }) {
  const s = route.stats;
  return (
    <button className={`card route ${selected ? "selected" : ""}`} onClick={() => onSelect(index)} aria-pressed={selected}>
      <div className="route-head">
        <span className="dot" style={{ background: ROUTE_COLORS[index] }} />
        <strong>{route.label}</strong>
        {recommended && <span className="tag">Recommended</span>}
        <span className="spacer" />
        <RiskBadge level={s.worst_level} />
      </div>
      <div className="route-summary">via {route.summary}</div>
      <div className="stats">
        <div>
          <b>{formatDuration(route.duration_s)}</b>
          <small>{route.extra_minutes_vs_fastest ? `+${route.extra_minutes_vs_fastest} min vs fastest` : "fastest"}</small>
        </div>
        <div>
          <b>{formatMiles(route.distance_miles)}</b>
          <small>distance</small>
        </div>
        <div>
          <b>{formatDateTime(route.arrival)}</b>
          <small>arrival</small>
        </div>
      </div>
      <RiskBar milesByLevel={s.miles_by_level} />
      <div className="risk-line">
        <span>Severe {Math.round(s.severe_miles)} mi</span>
        <span>High {Math.round(s.high_miles)} mi</span>
        <span>Avg risk {s.avg_risk.toFixed(2)}</span>
        {s.no_travel_miles > 0 && <span className="danger">No Travel {Math.round(s.no_travel_miles)} mi</span>}
      </div>
    </button>
  );
}
