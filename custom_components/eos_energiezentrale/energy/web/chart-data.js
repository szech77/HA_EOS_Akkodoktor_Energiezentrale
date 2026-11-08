/* Pure time-series sampling shared by charts and behavioral tests. */
(function (root) {
  'use strict';
  function points(rows, key, start, end) {
    return rows.flatMap(row => {
      const stamp = Date.parse(row.time);
      if (!Number.isFinite(stamp) || stamp < start || stamp > end || !Number.isFinite(row[key])) return [];
      return [{stamp, end:Date.parse(row.end), value:row[key]}];
    }).sort((a,b) => a.stamp-b.stamp);
  }

  function at(series, stamp, now) {
    if (stamp > now) {
      // Forecast energy/power belongs to its slot, never to an uncovered gap.
      const point = series.future.find(row => row.stamp <= stamp && stamp < row.end);
      return point ? {point,forecast:true} : null;
    }
    let nearest = null;
    for (const point of series.actual) {
      if (!nearest || Math.abs(point.stamp-stamp) < Math.abs(nearest.stamp-stamp)) nearest = point;
    }
    return nearest && Math.abs(nearest.stamp-stamp) <= 360000 ? {point:nearest,forecast:false} : null;
  }

  const api = Object.freeze({points,at});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EosChartData = api;
})(globalThis);
