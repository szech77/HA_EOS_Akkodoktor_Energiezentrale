"""Manufacturer-independent storage aggregation and constrained allocation."""
from math import isfinite


def total(values):
    return sum(values) if values and all(value is not None and isfinite(value) for value in values) else None


def distribute(watts, caps, weights):
    """Weighted water filling with hard per-device caps; never exceed a budget."""
    result=[0.]*len(caps)
    remaining=min(watts,sum(caps))
    active={index for index in range(len(caps)) if caps[index]>0 and weights[index]>0}
    while active and remaining>0:
        weight=sum(weights[index] for index in active)
        capped={index for index in active if remaining*weights[index]/weight>=caps[index]}
        if not capped:
            for index in active: result[index]=remaining*weights[index]/weight
            break
        for index in capped:
            result[index]=caps[index]
            remaining-=caps[index]
        active-=capped
    return result
