import { useCallback, useState } from "react";
import CheckpointTable from "./components/CheckpointTable";
import HeatControl from "./components/HeatControl";
import MapView from "./components/MapView";
import RouteCard from "./components/RouteCard";
import TripForm from "./components/TripForm";
import { planTrip } from "./lib/api";

export default function App() {
  const [plan, setPlan] = useState(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hour, setHour] = useState(0);
  const [heatEnabled, setHeatEnabled] = useState(true);
  const [focus, setFocus] = useState(null);

  const handleSubmit = useCallback(async (payload) => {
    setLoading(true);
    setError("");
    try {
      const result = await planTrip(payload);
      setPlan(result);
      setSelected(result.recommended_index);
      setHour(0);
      setFocus(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const selectRoute = (i) => {
    setSelected(i);
    setFocus(null);
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Compare three routes by weather risk at the time your truck actually gets there.</p>
        </header>
        <TripForm loading={loading} onSubmit={handleSubmit} />
        {error && <div className="card error" role="alert">{error}</div>}
        {loading && <div className="card loading">Finding routes and loading forecasts. Long trips can take up to 20 seconds…</div>}

        {plan && !loading && (
          <>
            <div className="card recommend">
              <small>Recommended</small>
              <h2>{plan.routes[plan.recommended_index].label}</h2>
              <p>{plan.recommendation_reason}</p>
            </div>
            {plan.routes.map((route, i) => (
              <RouteCard key={route.label} route={route} index={i} selected={i === selected} recommended={i === plan.recommended_index} onSelect={selectRoute} />
            ))}
            <CheckpointTable route={plan.routes[selected]} focusIndex={focus?.route === selected ? focus.index : -1} onFocus={(index) => setFocus({ route: selected, index })} />
          </>
        )}
      </aside>

      <main className="map-wrap">
        <MapView plan={plan} selected={selected} onSelect={selectRoute} hour={hour} heatEnabled={heatEnabled} focus={focus} />
        {plan && <HeatControl departure={plan.departure} hour={hour} onHour={setHour} enabled={heatEnabled} onToggle={setHeatEnabled} />}
      </main>
    </div>
  );
}
