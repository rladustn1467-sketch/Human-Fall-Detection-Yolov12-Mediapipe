"""HTTPS for the server (stage 3), on a COPY of the server with a development certificate (tools/dev_tls.py).

1. Direct TLS (uvicorn --ssl-*): the app, the old shared-token API and the device API work over HTTPS with the
   certificate checked (a client only trusts it when given the dev CA; the system trust store and another CA refuse it).
2. Behind a reverse proxy (the planned deployment: the proxy ends HTTPS and forwards to 127.0.0.1): the server uses
   X-Forwarded-Proto / X-Forwarded-For from the local proxy for Secure cookies and per-address limits.
3. The shared token never shows in the server's access log.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import http.client
import json
import ssl
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import dev_tls  # noqa: E402

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"H" * 64 + b"\xff\xd9").decode()


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


class HttpsServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.tls = dev_tls.write(Path(cls.tmp.name) / "dev")
        cls.other = dev_tls.write(Path(cls.tmp.name) / "other")         # 다른 CA (믿으면 안 되는 인증서)
        cls.server = ServerCopy(extra_args=["--ssl-keyfile", str(cls.tls["key"]), "--ssl-certfile", str(cls.tls["cert"])])
        cls.ctx = ssl.create_default_context(cafile=str(cls.tls["ca"]))

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.tmp.cleanup()

    def https(self, method, path, body=None, headers=None, ctx=None):
        c = http.client.HTTPSConnection("localhost", self.server.port, timeout=15, context=ctx or self.ctx)
        h = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        out = (r.status, {k.lower(): v for k, v in r.getheaders()}, raw)
        c.close()
        return out

    def json(self, *a, **k):
        status, headers, raw = self.https(*a, **k)
        return status, headers, (json.loads(raw) if raw.strip().startswith(b"{") else None)

    def test_health_over_https_with_the_dev_ca(self):
        status, _, data = self.json("GET", "/api/v2/health")
        self.assertEqual((status, data["ok"]), (200, True))

    def test_certificate_is_really_checked(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.https("GET", "/api/v2/health", ctx=ssl.create_default_context())              # 시스템 신뢰 목록
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.https("GET", "/api/v2/health", ctx=ssl.create_default_context(cafile=str(self.other["ca"])))
        plain = http.client.HTTPConnection("localhost", self.server.port, timeout=5)        # HTTPS 포트에 HTTP
        with self.assertRaises((http.client.HTTPException, ConnectionError, OSError)):
            plain.request("GET", "/api/v2/health")
            plain.getresponse().read()

    def test_app_login_cookie_is_secure(self):
        status, headers, _ = self.json("POST", "/api/v2/auth/signup", {"name": "보안시험", "phone": phone(), "password": PW},
                                       headers={"Origin": f"https://localhost:{self.server.port}"})
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"]
        self.assertIn("fd_session=", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)

    def test_device_pairing_and_fall_over_https(self):
        origin = {"Origin": f"https://localhost:{self.server.port}"}
        _, h, _ = self.json("POST", "/api/v2/auth/signup", {"name": "대상에이", "phone": phone(), "password": PW}, headers=origin)
        cookie = {"Cookie": h["set-cookie"].split(";", 1)[0], **origin}
        self.json("POST", "/api/v2/groups", headers=cookie)
        _, _, st = self.json("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}}, headers=cookie)
        home = st["state"]["homes"][0]["id"]
        _, _, p = self.json("POST", f"/api/v2/homes/{home}/devices/pairing", {"type": "phone", "location": "거실"}, headers=cookie)
        status, _, d = self.json("POST", "/api/v2/device/pair", {"code": p["pairing"]["code"]})
        self.assertEqual(status, 200)
        auth = {"Authorization": f"Bearer {d['deviceToken']}"}
        self.assertEqual(self.json("POST", "/api/v2/device/heartbeat", {"cameraOk": True}, headers=auth)[0], 200)
        status, _, f = self.json("POST", "/api/v2/device/events", {"event_id": uuid.uuid4().hex, "image_jpeg_base64": JPEG},
                                 headers=auth)
        self.assertEqual((status, f["image_saved"]), (200, True))
        _, _, st = self.json("GET", "/api/v2/state", headers=cookie)
        inc = next(i for i in st["state"]["incidents"] if i["id"] == f["incident_id"])
        status, headers, raw = self.https("GET", f"/api/v2/incidents/{inc['id']}/photos/{inc['photos'][0]['id']}.jpg", headers=cookie)
        self.assertEqual((status, headers["content-type"], raw[:3]), (200, "image/jpeg", b"\xff\xd8\xff"))
        self.assertFalse(d["deviceToken"] in (self.server.dir / "server.log").read_text(encoding="utf-8"),
                         "device token found in the server log")

    def test_old_shared_token_api_and_login_over_https(self):
        body = {"event_id": uuid.uuid4().hex, "device_id": "pc-old", "fall_type": "slip_and_fall", "is_test": True}
        status, _, data = self.json("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        self.assertEqual((status, data["ok"]), (200, True))
        status, headers, _ = self.https("GET", f"/login?token={self.server.token}&next=/app")
        self.assertEqual(status, 303)
        self.assertIn("Secure", headers["set-cookie"])
        self.assertEqual((headers["cache-control"], headers["referrer-policy"]), ("no-store", "no-referrer"))
        log = (self.server.dir / "server.log").read_text(encoding="utf-8")
        self.assertIn("/login?token=***", log)                                    # 접속 기록에는 가려서
        self.assertFalse(self.server.token in log, "shared token found in the server log")   # 시작 안내에도 없음 (값을 출력하지 않음)


class BehindProxyTest(unittest.TestCase):
    """The proxy on the same computer sends X-Forwarded-*; uvicorn trusts them only from 127.0.0.1 (its default)."""

    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def signup(self, headers):
        return self.server.request("POST", "/api/v2/auth/signup", {"name": "프록시", "phone": phone(), "password": PW},
                                   headers=headers)

    def test_forwarded_https_gives_secure_cookie(self):
        status, h, _ = self.signup({"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.10",
                                    "Origin": f"https://127.0.0.1:{self.server.port}"})
        self.assertEqual(status, 200)
        self.assertIn("Secure", h["set-cookie"])
        status, h, _ = self.signup({})                                            # 프록시 없이 HTTP
        self.assertEqual(status, 200)
        self.assertNotIn("Secure", h["set-cookie"])

    def test_limits_use_the_real_client_address(self):
        for _ in range(10):
            self.assertEqual(self.server.request("POST", "/api/v2/device/pair", {"code": "WRONG3"},
                                                 headers={"X-Forwarded-For": "203.0.113.7"})[0], 400)
        self.assertEqual(self.server.request("POST", "/api/v2/device/pair", {"code": "WRONG3"},
                                             headers={"X-Forwarded-For": "203.0.113.7"})[0], 429)   # 이 주소만 막힘
        self.assertEqual(self.server.request("POST", "/api/v2/device/pair", {"code": "WRONG3"},
                                             headers={"X-Forwarded-For": "203.0.113.8"})[0], 400)   # 다른 사람은 그대로


if __name__ == "__main__":
    unittest.main()
