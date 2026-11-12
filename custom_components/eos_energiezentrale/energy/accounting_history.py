"""Read-only reconstruction of older Influx measurements before ledger recording.

Five-minute means and gaps up to six hours are estimates. Initial battery value
uses the same price assumptions as the live model, without modifying live inventory.
"""
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_right
from datetime import datetime, time, timedelta, timezone

from .accounting import Accounting, add, empty
from .domain import house_only, instant, number
from .accounting_estimates import MAX_GAP_SECONDS, interpolate, repair


def reconstruct(config, report, now, vehicle_configs=()):
    start = datetime.combine(datetime.fromisoformat(report["date"]).date(), time(), config.zone).astimezone(timezone.utc)
    end = min(datetime.combine(datetime.fromisoformat(report["end"]).date(), time(), config.zone).astimezone(timezone.utc), now)
    recorded = instant(report.get("started"))
    if recorded is not None:
        end = min(end, recorded)
    if end <= start or not config.influx.url:
        return {}
    options = config.options
    power = [("W",1),("kW",1000)]
    sources = {key:(options[key+"_entity"], power) for key in ("pv","house","grid","heat")}
    sources["price"] = (options["price_entity"],[("EUR/kWh",100),("ct/kWh",1),("€/kWh",100)])
    battery = getattr(config.battery,"ids",{})
    for key,entity in (("battery_charge","charge_power"),("battery_discharge","discharge_power")):
        sources[key] = (battery.get(entity,""),power)
    sources["battery_soc"] = (battery.get("soc",""),[("%",1)])
    vehicle_keys = []
    if vehicle_configs:
        for identity,child in vehicle_configs:
            key = "car/"+identity
            vehicle_keys.append(key)
            sources[key] = (getattr(child.wallbox,"ids",{}).get("power",""),power)
    elif options.get("wallbox_type") != "none":
        sources["car"] = (getattr(config.wallbox,"ids",{}).get("power",""),power)

    def read(item):
        key,(entity,units)=item
        if not entity:
            return key, []
        return key,config.influx.history(entity,units,start=(start-timedelta(hours=1) if key in {"price","battery_soc"} else start).isoformat(),end=end.isoformat())

    rows = {}
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix="eos-report") as pool:
        for key,series in pool.map(read,sources.items()):
            for stamp,value in series:
                stamp = instant(stamp)
                if stamp is not None and number(value) is not None:
                    rows.setdefault(stamp,{})[key]=value
    model = object.__new__(Accounting)
    prices=sorted((stamp,row['price']) for stamp,row in rows.items() if number(row.get('price')) is not None)
    price_times=[stamp for stamp,_ in prices]
    model.settings = report["settings"]
    model.stock = None
    model.pv_tariff = report.get("pv_tariff")
    effective = report["effective"]
    consumers = {}
    prepared = []
    model.last_rate = None
    held = {}
    for stamp,row in sorted(rows.items()):
        # Prices are step values rather than power samples: an hourly tariff
        # remains valid between reports, but is never held across longer gaps.
        for field in ("price", "battery_soc"):
            if field in row:
                held[field] = (stamp,row[field])
            elif field in held and (stamp-held[field][0]).total_seconds() < 3600:
                row[field] = held[field][1]
        if not any(key in row for key in ('pv','house','grid','heat','battery_charge','battery_discharge','car',*vehicle_keys)):
            continue
        row["solar"] = row.get("pv")
        row["house_total"] = row.get("house")
        if vehicle_keys:
            row["car"] = sum(row[key] for key in vehicle_keys) if all(key in row for key in vehicle_keys) else None
        elif options.get("wallbox_type") == "none":
            row["car"] = 0
        if not options.get("heat_entity"):
            row["heat"] = 0
        row["house"] = house_only(row.get("house_total"),row.get("car"),row.get("heat"))
        row['consumers']={key:row.get(key) for key in ('house','heat','car',*vehicle_keys)}
        row['time']=stamp.isoformat()
        prepared.append((stamp,row))
    previous_stamp=None
    for index,(stamp,row) in enumerate(prepared):
        following=prepared[index+1] if index+1<len(prepared) else None
        gap=(following[0]-stamp).total_seconds() if following else 0
        bridge=300<gap<=MAX_GAP_SECONDS
        first=max(start,stamp)
        last=min(end,following[0] if bridge else stamp+timedelta(minutes=5))
        if following: last=min(last,following[0])
        if last<=first: continue
        if model.stock is None or (previous_stamp is not None and (stamp-previous_stamp).total_seconds()>300):
            model.reconcile_stock(row,effective)
        previous_stamp=stamp
        cursor=first
        while cursor<last:
            next_day=datetime.combine(cursor.astimezone(config.zone).date()+timedelta(days=1),time(),config.zone).astimezone(timezone.utc)
            next_hour=datetime.fromtimestamp((int(cursor.timestamp())//3600+1)*3600,timezone.utc)
            stop=min(last,next_day,next_hour,cursor+timedelta(minutes=5))
            price_index=bisect_right(price_times,cursor)-1
            if price_index+1<len(prices): stop=min(stop,prices[price_index+1][0])
            current=interpolate(row,following[1],((cursor-stamp).total_seconds()+(stop-cursor).total_seconds()/2)/gap) if bridge else repair(dict(row))
            current.update(time=cursor.isoformat(),estimated=True)
            if price_index>=0 and (cursor-prices[price_index][0]).total_seconds()<3600:
                current['price']=prices[price_index][1]
            amounts=model.allocate(current,(stop-cursor).total_seconds()/3600000,effective)
            local=cursor.astimezone(config.zone)
            key=(datetime.fromtimestamp(int(cursor.timestamp())//3600*3600,timezone.utc).isoformat() if report["period"]=="day"
                 else local.date().isoformat() if report["period"]=="month" else local.strftime("%Y-%m"))
            for name,amount in amounts.items():
                entry=consumers.setdefault(name,{"total":empty(),"bins":{}})
                add(entry["total"],amount)
                add(entry["bins"].setdefault(key,empty()),amount)
            cursor=stop
    return consumers


def merge_reconstruction(report, historical):
    for name,entry in historical.items():
        target=report["consumers"].setdefault(name,{"total":empty(),"bins":[]})
        add(target["total"],entry["total"])
        bins={row["time"]:row for row in target["bins"]}
        for stamp,amount in entry["bins"].items():
            add(bins.setdefault(stamp,{"time":stamp,**empty()}),amount)
        target["bins"]=[bins[key] for key in sorted(bins)]
    report["historical_consumers"] = {name:entry["total"] for name,entry in historical.items()}
    report["reconstructed"] = bool(historical)
    return report
