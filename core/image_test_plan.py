"""Bounded, deterministic image-test planning. No filesystem, model or queue writes.
Zetalvx Image Lab - SDXL Edition 0.1.0.27, Apache-2.0. Shared by preview and enqueue routes.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import product
from math import prod
import secrets

MAX_JOBS = 24
MAX_SEED = 2**31 - 2
# name: minimum, maximum, integer
AXES = {'cfg': (1, 20, False), 'steps': (1, 120, True),
        'strength': (0.01, 1, False), 'seed': (0, MAX_SEED, True)}
TASKS = {'generate', 'edit', 'inpaint', 'reference', 'multi_image'}


def number(value, name, low, high, integer=False):
    if isinstance(value, bool) or value is None:
        raise ValueError(f'{name}: number required')
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{name}: invalid number') from None
    if not dec.is_finite() or dec < Decimal(str(low)) or dec > Decimal(str(high)):
        raise ValueError(f'{name}: allowed range {low} … {high}')
    if integer and dec != dec.to_integral_value():
        raise ValueError(f'{name}: whole number required')
    return int(dec) if integer else float(dec)


def range_values(name, spec):
    if name not in AXES or not isinstance(spec, dict):
        raise ValueError(f'Unsupported test parameter: {name}')
    lo, hi, integer = AXES[name]
    minimum = number(spec.get('min'), name, lo, hi, integer)
    maximum = number(spec.get('max'), name, lo, hi, integer)
    count = number(spec.get('count'), f'{name} count', 1, MAX_JOBS, True)
    if maximum < minimum:
        raise ValueError(f'{name}: maximum must be at least minimum')
    if count > 1 and (maximum == minimum or (integer and count > maximum-minimum+1)):
        raise ValueError(f'{name}: not enough distinct values for {count} trials')
    a, b = Decimal(str(minimum)), Decimal(str(maximum))
    values = []
    for i in range(count):
        value = a if count == 1 else a + (b-a)*i/(count-1)
        value = int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if integer else float(value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
        if value in values:
            raise ValueError(f'{name}: range too small for {count} distinct values')
        values.append(value)
    return values


def array_values(name, raw, fallback):
    if raw is None:
        return [fallback]
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_JOBS:
        raise ValueError(f'{name}: expected 1 … {MAX_JOBS} values')
    out = []
    for value in raw:
        v = number(value, name, *AXES[name])
        if v not in out:
            out.append(v)
    return out


def plan_image_test(params, sweep, task, *, random_seed=None):
    """Validate before Cartesian expansion; a plan is at most MAX_JOBS images.

    Automatic profiles use explicit *_values arrays. Custom mode uses min/max/count
    ranges. Unselected axes retain the form's current value. Each job has batch=1.
    Returned base_seed can be put into a preview's request to freeze random seeds.
    """
    if not isinstance(params, dict) or not isinstance(sweep, dict) or task not in TASKS:
        raise ValueError('Invalid image test request')
    max_jobs = number(sweep.get('max_jobs', MAX_JOBS), 'max_jobs', 1, MAX_JOBS, True)
    mode = sweep.get('mode', 'automatic')
    if mode not in {'automatic', 'custom'}:
        raise ValueError('Unknown test mode')
    defaults = {'cfg': number(params.get('cfg', 7), 'CFG', 1, 20),
                'steps': number(params.get('steps', 30), 'Steps', 1, 120, True)}
    if task != 'generate':
        defaults['strength'] = number(params.get('strength', 0.35), 'Denoise', 0.01, 1)
    if mode == 'custom':
        ranges = sweep.get('ranges', {})
        if not isinstance(ranges, dict) or not ranges:
            raise ValueError('Select at least one parameter to test')
        for name in ranges:
            if name not in AXES or (name == 'strength' and task == 'generate'):
                raise ValueError(f'{name}: not available for this task')
        axes = {name: range_values(name, ranges[name]) if name in ranges else [val]
                for name, val in defaults.items()}
        if 'seed' in ranges:
            axes['seed'] = range_values('seed', ranges['seed'])
    else:
        axes = {name: array_values(name, sweep.get(name+'_values'), val)
                for name, val in defaults.items()}
    count = prod(len(values) for values in axes.values())
    if count > max_jobs:
        raise ValueError(f'Test would create {count} images; limit is {max_jobs}. Reduce values per parameter.')
    seed = number(params.get('seed', -1), 'Seed', -1, MAX_SEED, True)
    vary = sweep.get('vary_seed', False)
    if not isinstance(vary, bool):
        raise ValueError('vary_seed must be true or false')
    if 'seed' in axes and vary:
        raise ValueError('Choose either a seed range or a different seed per test, not both')
    if seed == -1:
        seed = axes['seed'][0] if 'seed' in axes else (random_seed or (lambda: secrets.randbelow(MAX_SEED+1)))()
        seed = number(seed, 'Seed', 0, MAX_SEED, True)
    variants = []
    for idx, values in enumerate(product(*axes.values())):
        variant = dict(zip(axes, values))
        variant.setdefault('seed', (seed+idx) % (MAX_SEED+1) if vary else seed)
        variant['index'] = idx+1
        variants.append(variant)
    return {'count': count, 'limit': max_jobs, 'mode': mode, 'task': task, 'axes': axes,
            'base_seed': seed, 'seed_policy': 'range' if 'seed' in axes else ('increment' if vary else 'fixed'),
            'variants': variants, 'images_per_job': 1}
