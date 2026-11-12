"""Display-only interpolation; never used as input for device control."""
from .domain import number

MAX_GAP_SECONDS=6*3600
FIELDS=('solar','grid','battery_charge','battery_discharge','battery_soc','house_total','house','heat','car','price')


def interpolate(before,after,fraction):
    result={'consumers':{},'estimated':True}
    for key in FIELDS:
        left,right=number(before.get(key)),number(after.get(key))
        result[key]=(left+(right-left)*fraction if left is not None and right is not None
                     else left if left is not None else right)
    # Interpolate net battery flow rather than creating simultaneous charge/discharge.
    if all(result[key] is not None for key in ('battery_charge','battery_discharge')):
        net=result['battery_charge']-result['battery_discharge']
        result['battery_charge'],result['battery_discharge']=max(0,net),max(0,-net)
    for key in before.get('consumers',{}).keys() & after.get('consumers',{}).keys():
        left,right=number(before['consumers'][key]),number(after['consumers'][key])
        result['consumers'][key]=(left+(right-left)*fraction if left is not None and right is not None
                                  else left if left is not None else right)
    return repair(result)


def repair(row):
    """Infer missing battery flow from the AC balance, without inventing zero readings."""
    if any(number(row.get(key)) is None for key in ('battery_charge','battery_discharge')):
        values=[number(row.get(key)) for key in ('solar','grid','house_total')]
        if all(value is not None for value in values):
            net=values[0]+values[1]-values[2]
            row={**row,'battery_charge':max(0,net),'battery_discharge':max(0,-net),'estimated':True}
    return row


def known_rate(stock):
    if stock is None: return None
    known=stock['kwh']-stock['unknown']
    return stock['cost']/known if known>1e-12 else None
