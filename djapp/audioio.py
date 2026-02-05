from __future__ import annotations
import sounddevice as sd


def list_input_devices():
    devs = sd.query_devices()
    out = []
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            out.append((i, d["name"]))
    return out


def resolve_input_device(device_cfg):
    """
    device_cfg can be:
      - int index
      - string substring to match device name
      - None: default
    """
    if device_cfg is None:
        return None

    if isinstance(device_cfg, int):
        return device_cfg

    if isinstance(device_cfg, str):
        want = device_cfg.lower().strip()
        devs = sd.query_devices()
        for i, d in enumerate(devs):
            if d.get("max_input_channels", 0) > 0 and want in d["name"].lower():
                return i
        raise ValueError(f"Could not find input device containing name: {device_cfg}")

    raise TypeError("audio.device must be int, str, or null")
