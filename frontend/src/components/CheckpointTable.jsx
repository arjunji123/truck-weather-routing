import { formatDateTime } from "../lib/format";
import RiskBadge from "./RiskBadge";

export default function CheckpointTable({ route, focusIndex, onFocus }) {
  return (
    <div className="card">
      <h3>{route.label} checkpoints</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c, i) => (
              <tr key={i} className={i === focusIndex ? "focus" : ""} onClick={() => onFocus(i)}>
                <td>{Math.round(c.mile)}</td>
                <td>{formatDateTime(c.eta)}</td>
                <td>{c.wind_mph.toFixed(0)} mph</td>
                <td>{c.rain_in_hr.toFixed(2)}</td>
                <td>{c.snow_in_hr.toFixed(2)}</td>
                <td>
                  <RiskBadge level={c.risk.level} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <small className="hint">Rain and snow in inches per hour. Click a row to find it on the map.</small>
    </div>
  );
}
