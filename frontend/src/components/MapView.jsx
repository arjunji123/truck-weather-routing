import L from "leaflet";
import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { buildCorridor, chunkScore } from "../lib/corridor";
import { formatDateTime } from "../lib/format";
import { LEVEL_COLORS, ROUTE_COLORS, scoreColor } from "../lib/risk";
import RiskBadge from "./RiskBadge";

const toLatLngs = (route) => route.geometry.map(([lon, lat]) => [lat, lon]);

function FitBounds({ plan }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const bounds = L.latLngBounds(plan.routes.flatMap(toLatLngs));
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [plan, map]);
  return null;
}

function PanTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.panTo(target, { animate: true });
  }, [target, map]);
  return null;
}

/**
 * Heatmap along the trip corridor. Every route is drawn as a wide, blurred
 * ribbon (a CSS blur on its own canvas pane). Moving the slider only changes
 * colours; geometry is built once per plan.
 */
function HeatCorridor({ routes, hour, enabled }) {
  const map = useMap();
  const items = useRef([]);
  const group = useRef(L.layerGroup());
  const corridors = useMemo(() => routes.map(buildCorridor), [routes]);

  useEffect(() => {
    if (!map.getPane("heat")) {
      const pane = map.createPane("heat");
      pane.style.zIndex = 380; // below route lines, above tiles
      pane.style.filter = "blur(9px)";
      pane.style.pointerEvents = "none";
    }
    const renderer = L.canvas({ pane: "heat", padding: 0.3 });
    group.current.clearLayers();
    items.current = corridors.flat().map((chunk) => {
      const line = L.polyline(chunk.latlngs, {
        renderer,
        pane: "heat",
        weight: 34,
        opacity: 0.7,
        lineCap: "round",
        lineJoin: "round",
        interactive: false,
        color: "#999",
      });
      group.current.addLayer(line);
      return { line, chunk, color: "" };
    });
  }, [map, corridors]);

  useEffect(() => {
    const layer = group.current;
    if (enabled) layer.addTo(map);
    else layer.remove();
    return () => layer.remove();
  }, [enabled, map, corridors]);

  useEffect(() => {
    for (const item of items.current) {
      const color = scoreColor(chunkScore(item.chunk, hour));
      if (color !== item.color) {
        item.color = color;
        item.line.setStyle({ color });
      }
    }
  }, [hour, corridors]);

  return null;
}

export default function MapView({ plan, selected, onSelect, hour, heatEnabled, focus }) {
  const focusPoint = focus ? plan.routes[focus.route].checkpoints[focus.index] : null;
  const order = plan ? [...plan.routes.keys()].sort((a, b) => (a === selected) - (b === selected)) : [];

  return (
    <MapContainer center={[39.5, -96]} zoom={4} preferCanvas className="map" zoomControl>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {plan && (
        <>
          <FitBounds plan={plan} />
          <PanTo target={focusPoint ? [focusPoint.lat, focusPoint.lon] : null} />
          <HeatCorridor routes={plan.routes} hour={hour} enabled={heatEnabled} />

          {order.map((i) => {
            const route = plan.routes[i];
            const active = i === selected;
            const positions = toLatLngs(route);
            return (
              <Polyline key={`line-${i}`} positions={positions} pathOptions={{ color: ROUTE_COLORS[i], weight: active ? 6 : 4, opacity: active ? 1 : 0.55 }} eventHandlers={{ click: () => onSelect(i) }}>
                <Tooltip sticky>
                  {route.label} · {route.summary}
                </Tooltip>
              </Polyline>
            );
          })}

          {order.map((i) =>
            plan.routes[i].checkpoints.map((c, k) => (
              <CircleMarker
                key={`cp-${i}-${k}`}
                center={[c.lat, c.lon]}
                radius={i === selected ? 7 : 4}
                pathOptions={{ color: "#fff", weight: i === selected ? 2 : 1, fillColor: LEVEL_COLORS[c.risk.level], fillOpacity: 1 }}
              >
                <Popup>
                  <div className="popup">
                    <b>
                      {plan.routes[i].label} · mile {Math.round(c.mile)}
                    </b>
                    <RiskBadge level={c.risk.level} />
                    <div>ETA {formatDateTime(c.eta)}</div>
                    <div>Wind {c.wind_mph.toFixed(0)} mph</div>
                    <div>Rain {c.rain_in_hr.toFixed(2)} in/hr</div>
                    <div>Snow {c.snow_in_hr.toFixed(2)} in/hr</div>
                    {!c.forecast_in_range && <div className="warn">Forecast not available for this time.</div>}
                  </div>
                </Popup>
              </CircleMarker>
            )),
          )}

          {focusPoint && <CircleMarker center={[focusPoint.lat, focusPoint.lon]} radius={13} pathOptions={{ color: "#111", weight: 3, fill: false }} />}

          <CircleMarker center={[plan.origin.lat, plan.origin.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#111", fillOpacity: 1 }}>
            <Tooltip permanent direction="top">Origin</Tooltip>
          </CircleMarker>
          <CircleMarker center={[plan.destination.lat, plan.destination.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#111", fillOpacity: 1 }}>
            <Tooltip permanent direction="top">Destination</Tooltip>
          </CircleMarker>
        </>
      )}
    </MapContainer>
  );
}
