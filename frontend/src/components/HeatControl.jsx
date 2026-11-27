import { useEffect, useState } from "react";
import { LEVEL_COLORS, LEVEL_NAMES } from "../lib/risk";

const MAX_HOUR = 48;

export default function HeatControl({ departure, hour, onHour, enabled, onToggle }) {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => onHour((h) => (h >= MAX_HOUR ? 0 : h + 1)), 450);
    return () => clearInterval(id);
  }, [playing, onHour]);

  const when = new Date(new Date(departure).getTime() + hour * 3600 * 1000);
  return (
    <div className="heat-control">
      <div className="heat-top">
        <label className="switch">
          <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
          Weather heatmap
        </label>
        <span className="when">
          +{hour}h · {when.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}
        </span>
      </div>
      <div className="heat-slider">
        <button type="button" className="play" onClick={() => setPlaying((p) => !p)} disabled={!enabled} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min="0"
          max={MAX_HOUR}
          value={hour}
          disabled={!enabled}
          onChange={(e) => onHour(Number(e.target.value))}
          aria-label="Forecast hour after departure"
        />
      </div>
      <div className="legend">
        {LEVEL_NAMES.map((name, i) => (
          <span key={name}>
            <i style={{ background: LEVEL_COLORS[i] }} />
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}
