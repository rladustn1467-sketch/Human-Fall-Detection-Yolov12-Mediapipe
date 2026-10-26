package com.humanfall.app.detect;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * This phone's connection to the server as a detection device (same rules as the PC's dashboard/device_link.py).
 *
 * The family member gets a 6-character pairing code in the app ('기기 추가' → 감지용 휴대폰); it is entered once on
 * this phone and the server gives it its own device token, kept only in the app's private storage (never in Git,
 * never shown). With the token: a status signal every minute (camera working or not; the answer says whether
 * detection is turned on in the app), falls with the silhouette photo, and turning detection on/off from here.
 * If the family deletes the device in the app, the server answers 401: the token is dropped and a 'revoked' mark
 * is kept so nothing is sent until the phone is connected again.
 *
 * A fall that could not be sent (no network, server error) is kept in memory with the same event id and sent again
 * after the next successful status signal (the server makes one incident per event id), for up to 10 minutes.
 */
public final class DeviceLink {
    /** Where the token and connection info are kept (app-private SharedPreferences on the phone). */
    public interface Store {
        String get(String key);

        void putAll(Map<String, String> values);

        void clear();
    }

    /** Waits between retries (replaced in tests). */
    public interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    public static final class Revoked extends Exception {
        Revoked(String message) {
            super(message);
        }
    }

    public static final String APP_VERSION = "android-2c";
    public static final int DEFAULT_HEARTBEAT_SECONDS = 60;
    static final long[] RETRY_DELAYS_MS = {1000, 2000, 4000};   // PC 프로그램과 같은 재시도 간격
    static final long PENDING_MAX_AGE_MS = 10 * 60 * 1000;
    static final int PENDING_MAX = 5;
    static final int TIMEOUT_MS = 8000;

    /** 통신 오류의 종류만 기록 (주소·토큰·내용은 남기지 않음). 안드로이드에서는 logcat 의 DeviceLink 태그로 보임 */
    private static final java.util.logging.Logger LOG = java.util.logging.Logger.getLogger("DeviceLink");

    private static void logFailure(String what, Exception e) {
        Throwable root = e;
        while (root.getCause() != null && root.getCause() != root) root = root.getCause();
        LOG.warning(what + " 실패: " + e.getClass().getSimpleName() + (root != e ? " (원인: " + root.getClass().getSimpleName() + ")" : ""));
    }

    private final Store store;
    private Sleeper sleeper = Thread::sleep;
    private final List<Pending> pending = new ArrayList<>();

    public volatile boolean serverEnabled = true;   // 앱(또는 이 폰)에서 감지를 켜 두었는지
    public volatile long lastOkAt = 0;              // 서버와 마지막으로 통신에 성공한 시각 (ms)
    public volatile String lastError = null;        // 사람에게 보여 줄 마지막 통신 문제

    private static final class Pending {
        final String eventId;
        final byte[] jpeg;
        final long at;

        Pending(String eventId, byte[] jpeg, long at) {
            this.eventId = eventId;
            this.jpeg = jpeg;
            this.at = at;
        }
    }

    public DeviceLink(Store store) {
        this.store = store;
        String enabled = store.get("enabled");
        serverEnabled = enabled == null || !enabled.equals("0");
    }

    void setSleeper(Sleeper sleeper) {
        this.sleeper = sleeper;
    }

    public synchronized boolean isPaired() {
        String t = store.get("token");
        return t != null && !t.isEmpty();
    }

    public synchronized boolean isRevoked() {
        return "1".equals(store.get("revoked"));
    }

    public synchronized String location() {
        return store.get("location");
    }

    public synchronized String deviceId() {
        return store.get("deviceId");
    }

    public synchronized String base() {
        return store.get("base");
    }

    synchronized int pendingCount() {
        return pending.size();
    }

    // ---- HTTP ----
    static final class Response {
        final int status;
        final JSONObject body;

        Response(int status, JSONObject body) {
            this.status = status;
            this.body = body;
        }

        String message(String fallback) {
            String m = body.optString("message", "");
            return m.isEmpty() ? fallback : m;
        }
    }

    static Response post(String base, String path, JSONObject body, String token) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(base + path).openConnection();
        try {
            c.setConnectTimeout(TIMEOUT_MS);
            c.setReadTimeout(TIMEOUT_MS);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
            byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream o = c.getOutputStream()) {
                o.write(data);
            }
            int status = c.getResponseCode();
            InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            String text = "";
            if (in != null) {
                try (InputStream i = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                    byte[] buf = new byte[4096];
                    int n;
                    while ((n = i.read(buf)) > 0) out.write(buf, 0, n);
                    text = out.toString("UTF-8");
                }
            }
            JSONObject json;
            try {
                json = text.trim().startsWith("{") ? new JSONObject(text) : new JSONObject();
            } catch (JSONException e) {
                json = new JSONObject();
            }
            return new Response(status, json);
        } finally {
            c.disconnect();
        }
    }

    private void markRevoked() {
        Map<String, String> v = new HashMap<>();
        v.put("revoked", "1");
        synchronized (this) {
            store.clear();          // 토큰은 지우고 '해제됨'만 남김
            store.putAll(v);
            pending.clear();
        }
        serverEnabled = true;
        lastError = "가족 앱에서 이 기기 연결이 해제됐어요";
    }

    // ---- 연결 · 해제 ----
    /** Sends the pairing code once. Returns null on success, else the message for the person. */
    public String pair(String base, String code) {
        String c = code == null ? "" : code.replaceAll("\\s+", "").toUpperCase();
        if (c.isEmpty()) return "연결 코드를 입력해 주세요.";
        Response r;
        try {
            JSONObject body = new JSONObject();
            body.put("code", c);
            body.put("appVersion", APP_VERSION);
            r = post(base, "/api/v2/device/pair", body, null);
        } catch (IOException | JSONException e) {
            logFailure("연결 코드 전송", e);
            return "서버에 연결할 수 없어요. 네트워크를 확인해 주세요.";
        }
        String token = r.body.optString("deviceToken", "");
        if (r.status != 200 || token.isEmpty()) return r.message("연결하지 못했어요 (HTTP " + r.status + ").");
        Map<String, String> v = new HashMap<>();
        v.put("base", base);
        v.put("token", token);
        v.put("deviceId", r.body.optString("deviceId"));
        v.put("type", r.body.optString("type"));
        v.put("location", r.body.optString("location"));
        v.put("enabled", "1");
        synchronized (this) {
            store.clear();
            store.putAll(v);
            pending.clear();
        }
        serverEnabled = true;
        lastError = null;
        lastOkAt = System.currentTimeMillis();
        return null;
    }

    /** Forget the connection on this phone only (the device stays in the app until deleted there). */
    public void forget() {
        synchronized (this) {
            store.clear();
            pending.clear();
        }
        serverEnabled = true;
        lastError = null;
    }

    private synchronized String token() {
        return store.get("token");
    }

    private synchronized void remember(String key, String value) {
        Map<String, String> v = new HashMap<>();
        v.put(key, value);
        store.putAll(v);
    }

    private void applyAnswer(JSONObject body) {
        serverEnabled = body.optBoolean("enabled", true);
        remember("enabled", serverEnabled ? "1" : "0");
        String loc = body.optString("location", "");
        if (!loc.isEmpty() && !loc.equals(location())) remember("location", loc);
        lastOkAt = System.currentTimeMillis();
        lastError = null;
    }

    // ---- 상태 신호 · 켜기/끄기 ----
    /** One status signal; never throws. Returns seconds until the next one. */
    public int heartbeat(boolean cameraOk) {
        String token = token();
        if (token == null) return DEFAULT_HEARTBEAT_SECONDS;
        Response r;
        try {
            JSONObject body = new JSONObject();
            body.put("cameraOk", cameraOk);
            body.put("appVersion", APP_VERSION);
            r = post(base(), "/api/v2/device/heartbeat", body, token);
        } catch (IOException | JSONException e) {
            logFailure("상태 신호", e);
            lastError = "서버에 연결할 수 없어요";
            return 10;   // 끊겼으면 조금 자주 다시 시도
        }
        if (r.status == 401) {
            markRevoked();
            return DEFAULT_HEARTBEAT_SECONDS;
        }
        if (r.status != 200) {
            lastError = r.message("서버 응답 오류 (HTTP " + r.status + ")");
            return 10;
        }
        applyAnswer(r.body);
        flushPending();
        return r.body.optInt("heartbeatSeconds", DEFAULT_HEARTBEAT_SECONDS);
    }

    /** Turn detection on/off from this phone (same flag as the app's). Returns null on success, else a message. */
    public String setEnabled(boolean enabled) {
        String token = token();
        if (token == null) return "먼저 가족 앱의 연결 코드로 연결해 주세요.";
        Response r;
        try {
            JSONObject body = new JSONObject();
            body.put("enabled", enabled);
            r = post(base(), "/api/v2/device/enabled", body, token);
        } catch (IOException | JSONException e) {
            lastError = "서버에 연결할 수 없어요";
            return "서버에 연결할 수 없어요. 네트워크를 확인한 뒤 다시 시도해 주세요.";
        }
        if (r.status == 401) {
            markRevoked();
            return "가족 앱에서 이 기기 연결이 해제됐어요. 새 연결 코드로 다시 연결해 주세요.";
        }
        if (r.status != 200) return r.message("바꾸지 못했어요 (HTTP " + r.status + ").");
        applyAnswer(r.body);
        return null;
    }

    private static final char[] B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".toCharArray();

    /** Standard base64 (java.util.Base64 needs Android 8; this app also runs on Android 7). */
    static String base64(byte[] data) {
        StringBuilder sb = new StringBuilder((data.length + 2) / 3 * 4);
        for (int i = 0; i < data.length; i += 3) {
            int b0 = data[i] & 0xff;
            int b1 = i + 1 < data.length ? data[i + 1] & 0xff : 0;
            int b2 = i + 2 < data.length ? data[i + 2] & 0xff : 0;
            sb.append(B64[b0 >> 2]).append(B64[((b0 & 3) << 4) | (b1 >> 4)]);
            sb.append(i + 1 < data.length ? B64[((b1 & 15) << 2) | (b2 >> 6)] : '=');
            sb.append(i + 2 < data.length ? B64[b2 & 63] : '=');
        }
        return sb.toString();
    }

    // ---- 낙상 ----
    /**
     * Send one fall (same event id on every retry). Returns the server answer.
     *
     * @throws Revoked     the token was refused (401, not retried)
     * @throws IOException no network / server error after the retries (the caller may keep it for later)
     */
    public JSONObject sendFall(String eventId, boolean isTest, byte[] jpeg) throws Revoked, IOException {
        String token = token();
        if (token == null) throw new Revoked("not paired");
        JSONObject body = new JSONObject();
        try {
            body.put("event_id", eventId);
            body.put("fall_type", LegacyFallLogic.DEFAULT_FALL_TYPE);
            body.put("is_test", isTest);
            if (jpeg != null) body.put("image_jpeg_base64", base64(jpeg));
        } catch (JSONException e) {
            throw new IOException(e);
        }
        IOException last = null;
        for (int attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
            if (attempt > 0) {
                try {
                    sleeper.sleep(RETRY_DELAYS_MS[attempt - 1]);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("interrupted");
                }
            }
            Response r;
            try {
                r = post(base(), "/api/v2/device/events", body, token);
            } catch (IOException e) {
                logFailure("낙상 전송", e);
                last = e;   // 네트워크 오류: 다시 시도
                continue;
            }
            if (r.status == 401) {
                markRevoked();
                throw new Revoked(r.message("401"));
            }
            if (r.status >= 500) {
                last = new IOException("HTTP " + r.status);
                continue;
            }
            if (r.status != 200 || !r.body.optBoolean("ok")) {
                throw new IllegalStateException(r.message("HTTP " + r.status));   // 잘못된 요청: 다시 보내도 같음
            }
            lastOkAt = System.currentTimeMillis();
            return r.body;
        }
        throw last != null ? last : new IOException("send failed");
    }

    /** Send now; if the network/server is down, keep it to send again after the next good status signal. */
    public JSONObject sendFallOrKeep(String eventId, byte[] jpeg) throws Revoked {
        try {
            return sendFall(eventId, false, jpeg);
        } catch (IOException e) {
            synchronized (this) {
                pending.add(new Pending(eventId, jpeg, System.currentTimeMillis()));
                while (pending.size() > PENDING_MAX) pending.remove(0);
            }
            lastError = "서버에 연결할 수 없어요 (낙상 기록을 보관했다가 다시 보내요)";
            return null;
        }
    }

    /** Resend kept falls (same event ids, so the server never makes a second incident). */
    void flushPending() {
        List<Pending> todo;
        synchronized (this) {
            long now = System.currentTimeMillis();
            for (Iterator<Pending> it = pending.iterator(); it.hasNext(); ) {
                if (now - it.next().at > PENDING_MAX_AGE_MS) it.remove();
            }
            todo = new ArrayList<>(pending);
        }
        for (Pending p : todo) {
            try {
                sendFall(p.eventId, false, p.jpeg);
                synchronized (this) {
                    pending.remove(p);
                }
            } catch (Revoked e) {
                return;
            } catch (IOException | RuntimeException e) {
                return;   // 아직 안 됨: 다음 상태 신호 때 다시
            }
        }
    }
}
