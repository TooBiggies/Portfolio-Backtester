from typing import Tuple

def load_config():
    """Load `backtester_config` and normalize initial weights if needed.

    Returns (cfg_module, initial_weights_normalized)
    """
    import backtester_config as cfg

    initial_w = getattr(cfg, 'INITIAL_WEIGHTS', None)
    if initial_w is None:
        # fall back to any variable name
        initial_w = getattr(cfg, 'INITIAL_W', [])

    try:
        total = sum(initial_w)
        if abs(total - 1.0) > 1e-9:
            if total == 0:
                raise ValueError('Initial weights sum to zero')
            initial_w = [w / total for w in initial_w]
    except Exception:
        # if something unexpected, leave as-is
        pass

    return cfg, initial_w
