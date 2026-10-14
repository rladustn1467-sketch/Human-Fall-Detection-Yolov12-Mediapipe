package com.humanfall.falldetect.net;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.json.JSONObject;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.io.IOException;
import java.net.ServerSocket;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * EventApi against a small fake server on the PC (FakeHttpServer): request format, token header,
 * retries with the same event id, and no retry on 401. Response shapes copy server/main.py.
 */
public class EventApiTest {
    private static final String TOKEN = "test-token-123";

    private FakeHttpServer server;
    private String baseUrl;
    private final List<String> requests = Collections.synchronizedList(new ArrayList<>());
    private final List<String> tokens = Collections.synchronizedList(new ArrayList<>());
    private final List<Long> sleeps = new ArrayList<>();
    /** status codes to return for POST /api/events, in order; 200 after the list runs out */
    private final List<Integer> postCodes = Collections.synchronizedList(new ArrayList<>());
    private final AtomicInteger postCount = new AtomicInteger();

    @Before
    public void startServer() throws IOException {
        server = new FakeHttpServer((method, path, headers, body) -> {
            requests.add(method + " " + path + " " + body);
            String token = headers.get("x-access-token");
            tokens.add(token);
            int code = 200;
            String reply;
            if (!TOKEN.equals(token)) {
                code = 401;
                reply = "{\"detail\":\"Unauthorized\"}";
            } else if (path.equals("/api/events") && method.equals("POST")) {
                int n = postCount.getAndIncrement();
                code = n < postCodes.size() ? postCodes.get(n) : 200;
                String eventId = new JSONObject(body).getString("event_id");
                reply = code == 200 ? "{\"ok\":true,\"event_id\":\"" + eventId + "\",\"image_saved\":false,\"count\":1}"
                        : "{\"detail\":\"error\"}";
            } else if (path.endsWith("/response")) {
                String response = new JSONObject(body).getString("response");
                reply = event(response, response.equals("safe") ? "안전 확인" : "도움 요청", 0, null);
            } else if (path.startsWith("/api/events/")) {
                reply = event("awaiting_response", "응답 대기", 17, null);
            } else {
                reply = "[]";
            }
            return new Object[]{code, reply};
        });
        baseUrl = "http://127.0.0.1:" + server.port() + "/";  // 끝의 / 는 잘라 냄
    }

    @After
    public void stopServer() throws IOException {
        server.close();
    }

    private EventApi api(String token) {
        return new EventApi(baseUrl, token, EventApi.DEFAULT_RETRY_DELAYS_MS, sleeps::add);
    }

    private static String event(String status, String label, int remaining, String report) {
        return "{\"event_id\":\"" + "a".repeat(32) + "\",\"device_id\":\"android-emulator\",\"status\":\"" + status
                + "\",\"status_label\":\"" + label + "\",\"remaining_seconds\":" + remaining
                + ",\"report_in_seconds\":null,\"is_test\":true,\"late_response\":false,"
                + "\"escalation\":{\"state\":\"idle\",\"report\":" + (report == null ? "null" : report) + "}}";
    }

    // ---- 요청 형식 ----

    @Test
    public void newEventIdHasServerFormat() {
        String id = EventApi.newEventId();
        assertTrue(id, id.matches("^[0-9a-f]{32}$"));  // server/main.py EVENT_ID_RE
        assertNotEquals(id, EventApi.newEventId());
    }

    @Test
    public void eventJsonMatchesDashboardFields() throws Exception {
        JSONObject json = EventApi.buildEventJson("b".repeat(32), "android-emulator", "slip_and_fall", true);
        assertEquals("b".repeat(32), json.getString("event_id"));
        assertEquals("android-emulator", json.getString("device_id"));
        assertEquals("slip_and_fall", json.getString("fall_type"));
        assertTrue(json.getBoolean("is_test"));
        assertFalse(json.has("image_jpeg_base64"));
    }

    // ---- 낙상 전송 ----

    @Test
    public void sendEventPostsWithToken() throws Exception {
        String id = EventApi.newEventId();
        assertEquals(id, api(TOKEN).sendEvent(id, "android-emulator", "slip_and_fall", true));
        assertEquals(1, requests.size());
        assertTrue(requests.get(0).startsWith("POST /api/events {"));
        assertEquals(TOKEN, tokens.get(0));
        assertTrue(sleeps.isEmpty());
    }

    @Test
    public void serverErrorsAreRetriedWithTheSameEventId() throws Exception {
        postCodes.add(500);
        postCodes.add(503);
        String id = EventApi.newEventId();
        assertEquals(id, api(TOKEN).sendEvent(id, "android-emulator", "slip_and_fall", true));
        assertEquals(3, requests.size());
        for (String request : requests) {
            assertTrue(request, request.contains("\"event_id\":\"" + id + "\""));
        }
        assertEquals(List.of(1000L, 2000L), sleeps);
    }

    @Test
    public void wrongTokenIsNotRetried() throws Exception {
        try {
            api("wrong").sendEvent(EventApi.newEventId(), "android-emulator", "slip_and_fall", true);
            fail("expected AUTH error");
        } catch (ApiException e) {
            assertEquals(ApiException.Kind.AUTH, e.kind);
            assertEquals(401, e.httpCode);
            assertFalse(e.isRetryable());
        }
        assertEquals(1, requests.size());
        assertTrue(sleeps.isEmpty());
    }

    @Test
    public void unreachableServerIsRetriedThenReported() throws Exception {
        int closedPort;
        try (ServerSocket socket = new ServerSocket(0)) {
            closedPort = socket.getLocalPort();
        }
        EventApi offline = new EventApi("http://127.0.0.1:" + closedPort, TOKEN, EventApi.DEFAULT_RETRY_DELAYS_MS, sleeps::add);
        try {
            offline.sendEvent(EventApi.newEventId(), "android-emulator", "slip_and_fall", true);
            fail("expected NETWORK error");
        } catch (ApiException e) {
            assertEquals(ApiException.Kind.NETWORK, e.kind);
        }
        assertEquals(List.of(1000L, 2000L, 4000L), sleeps);
    }

    @Test
    public void missingSettingsAreReportedWithoutARequest() throws Exception {
        try {
            api("").sendEvent(EventApi.newEventId(), "android-emulator", "slip_and_fall", true);
            fail("expected NOT_CONFIGURED");
        } catch (ApiException e) {
            assertEquals(ApiException.Kind.NOT_CONFIGURED, e.kind);
        }
        assertTrue(requests.isEmpty());
    }

    // ---- 상태 조회와 응답 ----

    @Test
    public void getEventParsesServerFields() throws Exception {
        EventStatus status = api(TOKEN).getEvent("a".repeat(32));
        assertEquals("GET /api/events/" + "a".repeat(32) + " ", requests.get(0));
        assertEquals(EventStatus.AWAITING_RESPONSE, status.status);
        assertEquals("응답 대기", status.statusLabel);
        assertEquals(17, status.remainingSeconds);
        assertNull(status.reportInSeconds);
        assertFalse(status.reported);
        assertTrue(status.isTest);
        assertEquals("android-emulator", status.deviceId);
    }

    @Test
    public void respondSendsTheAnswer() throws Exception {
        EventStatus status = api(TOKEN).respond("a".repeat(32), EventApi.RESPONSE_HELP);
        assertEquals("POST /api/events/" + "a".repeat(32) + "/response {\"response\":\"help_needed\"}", requests.get(0));
        assertEquals(EventStatus.HELP_NEEDED, status.status);
    }

    @Test(expected = IllegalArgumentException.class)
    public void respondRejectsUnknownAnswers() throws Exception {
        api(TOKEN).respond("a".repeat(32), "maybe");
    }

    @Test
    public void connectionCheckUsesTheEventList() throws Exception {
        api(TOKEN).checkConnection();
        assertEquals("GET /api/events?limit=1 ", requests.get(0));
    }

    // ---- 응답 해석 ----

    @Test
    public void reportedAndReportCountdownAreParsed() throws Exception {
        JSONObject json = new JSONObject(event("timeout", "응답 시간 초과", 0, "{\"time\":\"2026-10-14 16:00:00\"}"));
        json.put("report_in_seconds", 90);
        EventStatus status = EventStatus.fromJson(json);
        assertTrue(status.reported);
        assertEquals(Integer.valueOf(90), status.reportInSeconds);
    }

    @Test
    public void incompleteEventIsABadResponse() throws Exception {
        try {
            EventStatus.fromJson(new JSONObject("{\"event_id\":\"x\"}"));
            fail("expected BAD_RESPONSE");
        } catch (ApiException e) {
            assertEquals(ApiException.Kind.BAD_RESPONSE, e.kind);
        }
    }

    @Test
    public void httpErrorsMapToKinds() {
        assertEquals(ApiException.Kind.AUTH, EventApi.httpError(401).kind);
        assertEquals(ApiException.Kind.NOT_FOUND, EventApi.httpError(404).kind);
        assertEquals(ApiException.Kind.REJECTED, EventApi.httpError(422).kind);
        assertTrue(EventApi.httpError(503).isRetryable());
        assertFalse(EventApi.httpError(422).isRetryable());
    }
}
