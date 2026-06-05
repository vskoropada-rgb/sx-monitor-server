"""
collectors/usb.py — detect newly connected USB storage devices via PowerShell Get-PnpDevice.
collectors/usb.py — виявлення нових USB-пристроїв через PowerShell Get-PnpDevice.
"""
import subprocess
import json
import logging
import storage

logger = logging.getLogger(__name__)


def _get_usb_devices() -> list:
    """Query PnP devices of class USB/DiskDrive/USBSTOR with status OK.
    Запитує PnP-пристрої класу USB/DiskDrive/USBSTOR зі статусом OK."""
    cmd = (
        "Get-PnpDevice | "
        "Where-Object { $_.Class -in @('USB','DiskDrive','USBSTOR') -and $_.Status -eq 'OK' } | "
        "Select-Object InstanceId,FriendlyName | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        raw = result.stdout.strip()
        data = json.loads(raw)
        # PowerShell returns a dict (not a list) when there is a single result.
        # PowerShell повертає dict (не list) коли є лише один результат.
        return [data] if isinstance(data, dict) else data
    except Exception as e:
        logger.debug("USB device query error: %s", e)
        return []


def collect(config: dict) -> dict:
    """Return newly detected USB devices (seen for the first time this session).
    Повертає нові USB-пристрої (виявлені вперше)."""
    devices = _get_usb_devices()
    new_devices = []

    for dev in devices:
        instance_id = dev.get("InstanceId", "")
        friendly = dev.get("FriendlyName") or instance_id
        if not instance_id:
            continue
        if not storage.is_known_usb(instance_id):
            storage.register_usb(instance_id, str(friendly))
            new_devices.append({"instance_id": instance_id, "name": str(friendly)})

    return {
        "new_usb_devices": new_devices,
        "usb_device_count": len(devices),
    }
