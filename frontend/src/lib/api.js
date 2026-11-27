const BASE = import.meta.env.VITE_API_URL ?? "";
const MAX_ATTEMPTS = 3;

async function postPlan(body) {
  const res = await fetch(`${BASE}/api/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

// Used when the weather service rate limits the server: the browser asks it
// directly and returns rows of [lat, lon, start, wind, rain, snow].
async function fetchWeather({ url, params, chunk_size: size, cells }) {
  const rows = [];
  for (let i = 0; i < cells.length; i += size) {
    const chunk = cells.slice(i, i + size);
    const query = new URLSearchParams({
      ...params,
      latitude: chunk.map((c) => c[0]).join(","),
      longitude: chunk.map((c) => c[1]).join(","),
    });
    const res = await fetch(`${url}?${query}`);
    if (!res.ok) throw new Error(`Weather service failed (${res.status}). Please try again in a few minutes.`);
    const data = await res.json();
    // One location comes back as an object, several as a list.
    [data].flat().forEach(({ hourly }, j) => {
      rows.push([...chunk[j], hourly.time[0], hourly.wind_speed_10m, hourly.rain, hourly.snowfall]);
    });
  }
  return rows;
}

export async function planTrip(payload) {
  const weather = [];
  for (let attempt = 1; ; attempt++) {
    const { res, data } = await postPlan(weather.length ? { ...payload, weather } : payload);
    if (res.ok) return data;
    if (!data.weather_needed || attempt === MAX_ATTEMPTS) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    weather.push(...(await fetchWeather(data.weather_needed)));
  }
}
