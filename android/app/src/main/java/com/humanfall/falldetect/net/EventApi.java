package com.humanfall.falldetect.net;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

/**
 * Calls the existing fall server API (server/main.py) with the X-Access-Token header:
 *   POST /api/events                    a fall happened (same JSON as the PC dashboard)
 *   GET  /api/events/{id}               current state of that fall
 *   POST /api/events/{id}/response      the person's answer: "safe" or "help_needed"
 *   GET  /api/events?limit=1            connection/token check
 * Blocking calls: run them off the main thread. Plain Java + org.json, so it can be unit-tested
 * on the PC. Never logs or returns the token.
 */
public class EventApi {
    public static final String RESPONSE_SAFE = "safe";
    public static final String RESPONSE_HELP = "help_needed";
    /** PC 대시보드(_post_fall_event)와 같은 재시도 간격 */
    public static final long[] DEFAULT_RETRY_DELAYS_MS = {1000, 2000, 4000};

    private static final String TOKEN_HEADER = "X-Access-Token";
    private static final int CONNECT_TIMEOUT_MS = 5000;
    private static final int READ_TIMEOUT_MS = 10000;

    /** Waits between retries (replaceable in tests). */
    public interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    private final String baseUrl;
    private final String token;
    private final long[] retryDelaysMs;
    private final Sleeper sleeper;

    public EventApi(String baseUrl, String token) {
        this(baseUrl, token, DEFAULT_RETRY_DELAYS_MS, Thread::sleep);
    }

    public EventApi(String baseUrl, String token, long[] retryDelaysMs, Sleeper sleeper) {
        this.baseUrl = baseUrl == null ? "" : baseUrl.trim().replaceAll("/+$", "");
        this.token = token == null ? "" : token.trim();
        this.retryDelaysMs = retryDelaysMs.clone();
        this.sleeper = sleeper;
    }

    /** New event id: 32 lowercase hex characters, the format the server accepts (uuid4 hex). */
    public static String newEventId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    /** JSON body for POST /api/events (no image for now). */
    public static JSONObject buildEventJson(String eventId, String deviceId, String fallType, boolean isTest) {
        try {
            JSONObject json = new JSONObject();
            json.put("event_id", eventId);
            json.put("device_id", deviceId);
            json.put("fall_type", fallType);
            json.put("is_test", isTest);
            return json;
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    /**
     * Sends one fall event, retrying network/5xx failures with the SAME event id (the server
     * then records it only once). Returns the event id confirmed by the server.
     */
    public String sendEvent(String eventId, String deviceId, String fallType, boolean isTest)
            throws ApiException, InterruptedException {
        String body = buildEventJson(eventId, deviceId, fallType, isTest).toString();
        ApiException last = null;
        for (int attempt = 0; attempt <= retryDelaysMs.length; attempt++) {
            if (attempt > 0) {
                sleeper.sleep(retryDelaysMs[attempt - 1]);
            }
            try {
                JSONObject result = request("POST", "/api/events", body);
                if (!result.optBoolean("ok", false) || !eventId.equals(result.optString("event_id"))) {
                    throw new ApiException(ApiException.Kind.BAD_RESPONSE, 200, "서버가 낙상 기록을 확인해 주지 않았어요.");
                }
                return eventId;
            } catch (ApiException e) {
                last = e;
                if (!e.isRetryable()) {
                    throw e;
                }
            }
        }
        throw last;
    }

    public EventStatus getEvent(String eventId) throws ApiException {
        return EventStatus.fromJson(request("GET", "/api/events/" + eventId, null));
    }

    /** Sends the person's answer once (no automatic retry: the user can press again). */
    public EventStatus respond(String eventId, String response) throws ApiException {
        if (!RESPONSE_SAFE.equals(response) && !RESPONSE_HELP.equals(response)) {
            throw new IllegalArgumentException("response must be safe or help_needed");
        }
        try {
            String body = new JSONObject().put("response", response).toString();
            return EventStatus.fromJson(request("POST", "/api/events/" + eventId + "/response", body));
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Checks the address and token with GET /api/events?limit=1. */
    public void checkConnection() throws ApiException {
        requestRaw("GET", "/api/events?limit=1", null);
    }

    private JSONObject request(String method, String path, String body) throws ApiException {
        String text = requestRaw(method, path, body);
        try {
            return new JSONObject(text);
        } catch (JSONException e) {
            throw new ApiException(ApiException.Kind.BAD_RESPONSE, 200, "서버 응답을 이해할 수 없어요.", e);
        }
    }

    private String requestRaw(String method, String path, String body) throws ApiException {
        if (baseUrl.isEmpty() || token.isEmpty()) {
            throw new ApiException(ApiException.Kind.NOT_CONFIGURED, 0, "설정에서 서버 주소와 토큰을 먼저 입력해 주세요.");
        }
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(baseUrl + path).openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setUseCaches(false);
            conn.setRequestProperty(TOKEN_HEADER, token);
            conn.setRequestProperty("Accept", "application/json");
            if (body != null) {
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                conn.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(bytes);
                }
            }
            int code = conn.getResponseCode();
            if (code >= 200 && code < 300) {
                return readAll(conn.getInputStream());
            }
            throw httpError(code);
        } catch (ApiException e) {
            throw e;
        } catch (IOException | IllegalArgumentException e) {
            // IllegalArgumentException: 주소 형식이 잘못된 경우 (예: http:// 없음)
            throw new ApiException(ApiException.Kind.NETWORK, 0,
                    "서버에 연결할 수 없어요. 서버가 켜져 있는지, 주소가 맞는지 확인해 주세요.", e);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    static ApiException httpError(int code) {
        if (code == 401) {
            return new ApiException(ApiException.Kind.AUTH, code, "토큰이 맞지 않아요. 설정에서 토큰을 확인해 주세요.");
        }
        if (code == 404) {
            return new ApiException(ApiException.Kind.NOT_FOUND, code, "서버에서 이 낙상 기록을 찾을 수 없어요.");
        }
        if (code >= 500) {
            return new ApiException(ApiException.Kind.SERVER, code,
                    String.format(Locale.ROOT, "서버 오류가 났어요 (HTTP %d).", code));
        }
        return new ApiException(ApiException.Kind.REJECTED, code,
                String.format(Locale.ROOT, "서버가 요청을 받지 않았어요 (HTTP %d).", code));
    }

    private static String readAll(InputStream in) throws IOException {
        try (InputStream input = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = input.read(buffer)) != -1) {
                out.write(buffer, 0, n);
            }
            return out.toString("UTF-8");
        }
    }
}
