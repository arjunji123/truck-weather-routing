/**
 * Prepares a route for the heatmap corridor.
 *
 * The route line is cut into short chunks. Each chunk remembers which two
 * weather samples surround it, so for any forecast hour its risk score is a
 * cheap interpolation. That keeps the slider fast (no network, no re-geometry).
 */
const MILE_M = 1609.344;

function haversineM([lat1, lon1], [lat2, lon2]) {
  const rad = Math.PI / 180;
  const a =
    Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * 6371008.8 * Math.asin(Math.sqrt(a));
}

export function buildCorridor(route) {
  const latlngs = route.geometry.map(([lon, lat]) => [lat, lon]);
  const miles = [0];
  for (let i = 1; i < latlngs.length; i++) {
    miles.push(miles[i - 1] + haversineM(latlngs[i - 1], latlngs[i]) / MILE_M);
  }
  const total = miles[miles.length - 1] || 1;
  const chunkMiles = Math.max(4, total / 200);
  const samples = route.heat;

  const chunks = [];
  let start = 0;
  let sampleIdx = 0;
  for (let i = 1; i < latlngs.length; i++) {
    if (miles[i] - miles[start] < chunkMiles && i < latlngs.length - 1) continue;
    const mid = (miles[start] + miles[i]) / 2;
    while (sampleIdx < samples.length - 2 && samples[sampleIdx + 1].mile < mid) sampleIdx++;
    const a = samples[sampleIdx];
    const b = samples[Math.min(sampleIdx + 1, samples.length - 1)];
    const span = b.mile - a.mile || 1;
    chunks.push({
      latlngs: latlngs.slice(start, i + 1),
      a: a.levels,
      b: b.levels,
      t: Math.max(0, Math.min(1, (mid - a.mile) / span)),
    });
    start = i;
  }
  return chunks;
}

export function chunkScore(chunk, hour) {
  return chunk.a[hour] + (chunk.b[hour] - chunk.a[hour]) * chunk.t;
}
