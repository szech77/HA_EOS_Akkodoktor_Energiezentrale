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

  function dailySolar(rows, now, zone) {
    const formatter = new Intl.DateTimeFormat('sv-SE',{timeZone:zone});
    const date = stamp => formatter.format(new Date(stamp));
    const today = date(now);
    const calendar = new Date(today+'T12:00:00Z');
    const boundary = key => {
      const center=Date.parse(key+'T00:00:00Z');
      let low=center-36*3600000, high=center+36*3600000;
      while(high-low>1) {
        const middle=Math.floor((low+high)/2);
        if(date(middle)<key) low=middle; else high=middle;
      }
      return high;
    };
    const keys=Array.from({length:4},(_,i)=>new Date(calendar.getTime()+i*86400000).toISOString().slice(0,10));
    return keys.slice(0,3).map((key,i)=>{
      const start=Math.max(now,boundary(key)), end=boundary(keys[i+1]);
      let cursor=start,wh=0,covered=0;
      const slots=points(rows,'solar',now-86400000,now+4*86400000);
      for(const row of slots) {
        const from=Math.max(start,cursor,row.stamp), to=Math.min(end,row.end);
        if(row.value<0 || !Number.isFinite(to) || to<=from) continue;
        wh+=row.value*(to-from)/3600000;
        covered+=to-from;
        cursor=to;
      }
      return {date:key,kwh:covered ? wh/1000 : null,complete:covered>=end-start,coveredMs:covered};
    });
  }

  const api = Object.freeze({points,at,dailySolar});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EosChartData = api;
})(globalThis);
