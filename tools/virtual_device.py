"""A virtual detection device for tests: does what a real phone does, through the same device API, without a camera.

It proves the server side of the device flow only. It says nothing about a real phone's camera, battery or network.
Never point it at the production server.

As a module:
    device = VirtualDevice("http://127.0.0.1:8012")
    device.pair("ABC123"); device.heartbeat(); device.fall(jpeg=b"...")

From the command line (the token stays in the state file and is never printed):
    python tools/virtual_device.py http://127.0.0.1:8012 state.json pair ABC123
    python tools/virtual_device.py http://127.0.0.1:8012 state.json heartbeat [ok|camera-bad]
    python tools/virtual_device.py http://127.0.0.1:8012 state.json fall [photo.jpg] [--test]
    python tools/virtual_device.py http://127.0.0.1:8012 state.json enabled on|off
"""
import base64
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class VirtualDevice:
    def __init__(self, base, token=None):
        self.base = base.rstrip("/")
        self.token = token
        self.device_id = None

    def call(self, path, body):
        """Returns (status, data), also for error answers."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def pair(self, code):
        status, data = self.call("/api/v2/device/pair", {"code": code, "appVersion": "virtual-device"})
        if status == 200:
            self.token, self.device_id = data["deviceToken"], data["deviceId"]
        return status, {k: v for k, v in data.items() if k != "deviceToken"}

    def heartbeat(self, camera_ok=True):
        return self.call("/api/v2/device/heartbeat", {"cameraOk": camera_ok, "appVersion": "virtual-device"})

    def enabled(self, on):
        return self.call("/api/v2/device/enabled", {"enabled": on})

    def unpair(self):
        return self.call("/api/v2/device/unpair", {})

    def fall(self, jpeg=None, event_id=None, test=False):
        body = {"event_id": event_id or uuid.uuid4().hex, "fall_type": "slip_and_fall", "is_test": test}
        if jpeg:
            body["image_jpeg_base64"] = base64.b64encode(jpeg).decode()
        return self.call("/api/v2/device/events", body)


def main(argv):
    base, state, cmd, args = argv[1], Path(argv[2]), argv[3], argv[4:]
    saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
    device = VirtualDevice(base, saved.get("deviceToken"))
    if cmd == "pair":
        status, data = device.pair(args[0])
        if status == 200:
            state.write_text(json.dumps({"deviceToken": device.token, "deviceId": device.device_id}), encoding="utf-8")
    elif cmd == "heartbeat":
        status, data = device.heartbeat((args[:1] or ["ok"])[0] == "ok")
    elif cmd == "enabled":
        status, data = device.enabled(args[0] == "on")
    elif cmd == "fall":
        photos = [a for a in args if not a.startswith("--")]
        status, data = device.fall(Path(photos[0]).read_bytes() if photos else None, test="--test" in args)
    else:
        raise SystemExit(f"알 수 없는 명령: {cmd}")
    print(json.dumps({"status": status, **data}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
