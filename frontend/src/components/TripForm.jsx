import { useState } from "react";
import { toLocalInputValue } from "../lib/format";

const INTERVALS = [10, 25, 50];

function defaultDeparture() {
  const d = new Date(Date.now() + 2 * 3600 * 1000);
  d.setMinutes(0, 0, 0);
  return toLocalInputValue(d);
}

export default function TripForm({ loading, onSubmit }) {
  const [origin, setOrigin] = useState("Chicago, IL");
  const [destination, setDestination] = useState("Dallas, TX");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState(35000);
  const [interval, setInterval] = useState(25);

  function submit(e) {
    e.preventDefault();
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(), // browser local time -> UTC
      load_lb: Number(load),
      interval_miles: interval,
    });
  }

  return (
    <form className="card form" onSubmit={submit}>
      <label>
        Origin
        <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="City, address or lat,lon" required />
      </label>
      <label>
        Destination
        <input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="City, address or lat,lon" required />
      </label>
      <div className="row">
        <label>
          Departure (your local time)
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </label>
        <label>
          Load weight (lb)
          <input type="number" min="0" max="150000" step="500" value={load} onChange={(e) => setLoad(e.target.value)} required />
        </label>
      </div>
      <div className="field">
        <span>Weather checkpoint every</span>
        <div className="segmented" role="radiogroup" aria-label="Checkpoint interval">
          {INTERVALS.map((miles) => (
            <button
              type="button"
              key={miles}
              role="radio"
              aria-checked={interval === miles}
              className={interval === miles ? "active" : ""}
              onClick={() => setInterval(miles)}
            >
              {miles} mi
            </button>
          ))}
        </div>
      </div>
      <button className="primary" disabled={loading}>
        {loading ? "Analysing routes…" : "Find safest route"}
      </button>
    </form>
  );
}
