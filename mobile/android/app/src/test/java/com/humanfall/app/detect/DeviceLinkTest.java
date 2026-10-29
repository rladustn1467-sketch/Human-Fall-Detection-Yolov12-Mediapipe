package com.humanfall.app.detect;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.json.JSONObject;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

/** DeviceLink against a fake server that follows the device API (2a) and can fail on purpose. */
public class DeviceLinkTest {
    static final String TOKEN = "tok-test-1";

    /** In-memory version of the app-private SharedPreferences. */
    static final class MemStore implements DeviceLink.Store {
        final Map<String, String> m = new HashMap<>();

        public String get(String k) { return m.get(k); }

        public void putAll(Map<String, String> v) { m.putAll(v); }

        public void clear() { m.clear(); }
    }

    FakeHttpServer server;
    String base;
    volatile boolean enabled = true;
    volatile String location = "거실";
    volatile int failEvents = 0;          // 다음 낙상 요청 몇 번을 500 으로
    volatile int eventStatus = 200;       // 그 뒤의 응답 코드
    volatile boolean revoked = false;
    volatile boolean down = false;        // 서버가 응답하지 못함 (503)
    volatile boolean unpaired = false;
    volatile boolean revokedEnabledOnly = false;   // 켜짐/꺼짐 알림만 500
    volatile String rejectEvent = null;            // 이 event id 는 400 (잘못된 요청)
    final List<String> eventIds = Collections.synchronizedList(new ArrayList<>());
    final List<JSONObject> eventBodies = Collections.synchronizedList(new ArrayList<>());

    private boolean authorized(Map<String, String> headers) {
        return !revoked && ("Bearer " + TOKEN).equals(headers.get("authorization"));
    }

    private Object[] handle(String method, String path, Map<String, String> headers, String text) throws Exception {
        JSONObject b = text.trim().startsWith("{") ? new JSONObject(text) : new JSONObject();
        if (down) return new Object[]{503, "{}"};
        String answer = "{\"enabled\":%s,\"location\":\"%s\",\"heartbeatSeconds\":60}";
        switch (path) {
            case "/api/v2/device/pair":
                if ("GOOD12".equals(b.optString("code"))) {
                    return new Object[]{200, "{\"deviceId\":\"d_1\",\"deviceToken\":\"" + TOKEN + "\",\"type\":\"phone\",\"location\":\"거실\",\"heartbeatSeconds\":60}"};
                }
                return new Object[]{400, "{\"message\":\"연결 코드를 확인해 주세요.\",\"field\":\"code\"}"};
            case "/api/v2/device/heartbeat":
                if (!authorized(headers)) return new Object[]{401, "{\"message\":\"기기 인증에 실패했어요.\"}"};
                return new Object[]{200, String.format(answer, enabled, location)};
            case "/api/v2/device/enabled":
                if (!authorized(headers)) return new Object[]{401, "{}"};
                if (revokedEnabledOnly) return new Object[]{500, "{}"};
                enabled = b.optBoolean("enabled");
                return new Object[]{200, String.format(answer, enabled, location)};
            case "/api/v2/device/unpair":
                if (!authorized(headers)) return new Object[]{401, "{}"};
                unpaired = true;
                revoked = true;
                return new Object[]{200, "{\"ok\":true}"};
            case "/api/v2/device/events":
                if (!authorized(headers)) return new Object[]{401, "{\"message\":\"기기 인증에 실패했어요.\"}"};
                eventIds.add(b.optString("event_id"));
                eventBodies.add(b);
                if (failEvents > 0) { failEvents--; return new Object[]{500, "{}"}; }
                if (b.optString("event_id").equals(rejectEvent)) return new Object[]{400, "{\"message\":\"잘못된 요청\"}"};
                if (eventStatus != 200) return new Object[]{eventStatus, "{\"message\":\"잘못된 요청\"}"};
                if (!enabled && !b.optBoolean("is_test")) return new Object[]{200, "{\"ok\":true,\"ignored\":\"off\"}"};   // 서버와 같음
                return new Object[]{200, "{\"ok\":true,\"incident_id\":\"inc_1\",\"image_saved\":" + b.has("image_jpeg_base64") + "}"};
            default:
                return new Object[]{404, "{}"};
        }
    }

    @Before
    public void start() throws IOException {
        server = new FakeHttpServer(this::handle);
        base = "http://127.0.0.1:" + server.port();
    }

    @After
    public void stop() throws IOException {
        server.close();
    }

    private DeviceLink paired(MemStore store, List<Long> waits) {
        DeviceLink link = new DeviceLink(store);
        link.setSleeper(waits::add);
        assertNull(link.pair(base, " good12 "));
        return link;
    }

    @Test
    public void pairWrongThenRightCode() {
        MemStore store = new MemStore();
        DeviceLink link = new DeviceLink(store);
        assertEquals("연결 코드를 입력해 주세요.", link.pair(base, ""));
        assertEquals("연결 코드를 확인해 주세요.", link.pair(base, "ZZZZZZ"));
        assertFalse(link.isPaired());
        assertNull(link.pair(base, "good12"));                              // 소문자도 받음
        assertTrue(link.isPaired());
        assertEquals(TOKEN, store.get("token"));                            // 앱 전용 저장소에만
        assertEquals("d_1", link.deviceId());
        assertEquals(base, link.base());
        assertEquals("서버에 연결할 수 없어요. 네트워크를 확인해 주세요.", new DeviceLink(new MemStore()).pair("http://127.0.0.1:1", "GOOD12"));
    }

    @Test
    public void onOffIsDecidedOnThisPhoneNotByTheServer() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        assertEquals(60, link.heartbeat(true));
        assertTrue(link.enabled);
        enabled = false;                                                    // 서버 값이 '꺼짐'이 돼도 (예: 예전 원격 끄기)
        location = "안방";
        link.heartbeat(true);
        assertTrue(link.enabled);                                           // 이 휴대폰은 켜진 채로
        assertTrue(enabled);                                                // 서버를 이 휴대폰 값('켜짐')으로 되돌림
        assertEquals("안방", link.location());                              // 위치 이름은 앱에서 바꿀 수 있음
        assertNull(link.setEnabled(false));                                 // 이 휴대폰에서 끔 → 서버도 꺼짐
        assertFalse(enabled);
        assertFalse(new DeviceLink(store).enabled);                         // 다시 켜도 꺼짐 기억
        enabled = true;                                                     // 서버 값이 '켜짐'이 돼도
        link.heartbeat(true);
        assertFalse(link.enabled);                                          // 서버 값으로 켜지지 않음
        assertFalse(enabled);
        assertNull(link.setEnabled(true));
        assertTrue(link.enabled);
        assertTrue(enabled);
    }

    @Test
    public void onOffWithoutNetworkAppliesHereAndIsSentLater() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        down = true;
        String note = link.setEnabled(false);
        assertEquals("감지를 껐어요. 서버에는 연결되면 알려요.", note);       // 이 휴대폰에서는 바로 꺼짐
        assertFalse(link.enabled);
        assertTrue(enabled);
        down = false;
        link.heartbeat(false);
        assertFalse(enabled);                                               // 다음 상태 신호 때 서버에도
        assertFalse(link.enabled);
    }

    @Test
    public void fallIsRetriedWithTheSameEventId() throws Exception {
        List<Long> waits = new ArrayList<>();
        DeviceLink link = paired(new MemStore(), waits);
        failEvents = 2;
        JSONObject r = link.sendFall("e1", false, new byte[]{(byte) 0xff, (byte) 0xd8, 1, 2});
        assertTrue(r.getBoolean("image_saved"));
        assertEquals(List.of("e1", "e1", "e1"), eventIds);                 // 같은 event id 로 3번
        assertEquals(List.of(1000L, 2000L), waits);
        assertEquals("/9gBAg==", eventBodies.get(0).getString("image_jpeg_base64"));
        eventStatus = 400;
        try {
            link.sendFall("e2", false, null);
            fail("4xx must not be retried");
        } catch (IllegalStateException expected) {
            assertEquals(4, eventIds.size());                               // 한 번만
        }
    }

    @Test
    public void serverStillOffWhileThisPhoneIsOnSyncsAndSendsAgain() throws Exception {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        enabled = false;                                                    // 서버에는 아직 '꺼짐' (켬을 못 알린 사이)
        JSONObject r = link.sendFallOrKeep("e1", new byte[]{1});
        assertEquals("inc_1", r.optString("incident_id"));                 // 무시되지 않고 사고가 됨
        assertTrue(enabled);                                                // 서버도 이 휴대폰 값(켜짐)으로 맞춤
        assertEquals(List.of("e1", "e1"), eventIds);                       // 같은 event id 로 한 번 더 (사고는 하나)
        assertEquals(0, link.pendingCount());
    }

    @Test
    public void serverStillOffAndSyncFailsKeepsTheFall() throws Exception {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        enabled = false;
        revokedEnabledOnly = true;                                          // 켜짐 알림만 실패 (500)
        assertNull(link.sendFallOrKeep("e3", new byte[]{1}));
        assertEquals(1, link.pendingCount());                               // 버리지 않고 보관했다가 다시
        revokedEnabledOnly = false;
        link.heartbeat(true);                                               // 다음 상태 신호: 켜짐을 알리고 다시 보냄
        assertTrue(enabled);
        assertEquals(0, link.pendingCount());
        assertEquals("e3", eventIds.get(eventIds.size() - 1));
    }

    @Test
    public void thisPhoneOffLeavesTheFallIgnored() throws Exception {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        assertNull(link.setEnabled(false));                                 // 이 휴대폰에서 끔 → 서버도 꺼짐
        JSONObject r = link.sendFallOrKeep("e2", new byte[]{1});
        assertEquals("off", r.optString("ignored"));                       // 꺼 둔 상태는 그대로 무시
        assertFalse(enabled);
        assertEquals(List.of("e2"), eventIds);                             // 다시 보내지 않음
    }

    @Test
    public void unsentFallSurvivesAnAppRestart() throws Exception {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        byte[] photo = new byte[300];
        new Random(7).nextBytes(photo);
        failEvents = 4;
        assertNull(link.sendFallOrKeep("e7", photo));
        assertEquals(1, link.pendingCount());
        DeviceLink restarted = new DeviceLink(store);                       // 앱이 꺼졌다 다시 켜짐 (같은 저장소)
        restarted.setSleeper(ms -> { });
        assertEquals(1, restarted.pendingCount());
        restarted.heartbeat(true);
        assertEquals(0, restarted.pendingCount());
        assertEquals("e7", eventIds.get(eventIds.size() - 1));
        JSONObject sent = eventBodies.get(eventBodies.size() - 1);
        assertArrayEquals(photo, java.util.Base64.getDecoder().decode(sent.getString("image_jpeg_base64")));   // 사진도 그대로
        assertEquals(0, new DeviceLink(store).pendingCount());              // 보낸 뒤에는 저장소에서도 지움
    }

    @Test
    public void rejectedFallDoesNotBlockTheOthers() throws Exception {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        failEvents = 8;                                                     // 두 낙상 모두 보관
        assertNull(link.sendFallOrKeep("bad", null));
        assertNull(link.sendFallOrKeep("good", null));
        assertEquals(2, link.pendingCount());
        rejectEvent = "bad";                                                // 서버가 이 낙상은 거절 (400, 다시 보내도 같음)
        link.heartbeat(true);
        assertEquals(0, link.pendingCount());                               // 거절된 것은 버리고 다음 것은 보냄
        assertEquals("good", eventIds.get(eventIds.size() - 1));
    }

    @Test
    public void unsentFallIsKeptAndSentAgainOnce() throws Exception {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        failEvents = 4;                                                     // 재시도 3번까지 모두 실패
        assertNull(link.sendFallOrKeep("e9", new byte[]{1}));
        assertEquals(1, link.pendingCount());
        assertTrue(link.lastError.contains("보관"));
        link.heartbeat(true);                                               // 서버가 다시 됨 → 보관한 낙상 전송
        assertEquals(0, link.pendingCount());
        assertEquals(5, eventIds.size());
        assertTrue(eventIds.stream().allMatch("e9"::equals));               // 같은 event id → 서버는 사고 하나
        link.heartbeat(true);
        assertEquals(5, eventIds.size());                                   // 다시 보내지 않음
    }

    @Test
    public void networkDownHeartbeatRetriesSoon() throws IOException {
        DeviceLink link = paired(new MemStore(), new ArrayList<>());
        server.close();
        assertEquals(10, link.heartbeat(true));
        assertEquals("서버에 연결할 수 없어요", link.lastError);
        assertTrue(link.isPaired());                                        // 끊겨도 연결 정보는 그대로
    }

    @Test
    public void revokedTokenIsDroppedAndRemembered() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        revoked = true;                                                     // 가족 앱에서 기기 삭제
        link.heartbeat(true);
        assertFalse(link.isPaired());
        assertTrue(link.isRevoked());
        assertNull(store.get("token"));
        DeviceLink restarted = new DeviceLink(store);                       // 앱을 다시 켜도
        assertTrue(restarted.isRevoked());
        try {
            restarted.sendFall("e3", false, null);
            fail("not paired");
        } catch (DeviceLink.Revoked expected) {
            // 보내지 않음
        } catch (IOException e) {
            fail(e.toString());
        }
        revoked = false;
        assertNull(restarted.pair(base, "GOOD12"));                         // 새 코드로 다시 연결
        assertFalse(restarted.isRevoked());
        restarted.forget();
        assertFalse(restarted.isPaired());
        assertFalse(restarted.isRevoked());
    }

    @Test
    public void base64MatchesTheStandard() {
        Random r = new Random(7);
        for (int n = 0; n < 50; n++) {
            byte[] b = new byte[r.nextInt(40)];
            r.nextBytes(b);
            assertEquals(java.util.Base64.getEncoder().encodeToString(b), DeviceLink.base64(b));
        }
        assertArrayEquals(new byte[0], java.util.Base64.getDecoder().decode(DeviceLink.base64(new byte[0])));
    }

    // ---- 로그아웃 정지 ('이 휴대폰'으로 감지하던 사람이 로그아웃) ----
    @Test
    public void logoutHoldTurnsDetectionOffHereAndOnTheServer() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        link.heartbeat(true);
        assertTrue(link.enabled);
        assertTrue(link.holdForLogout());                                   // 서버에도 '꺼짐'
        assertFalse(enabled);
        assertFalse(link.enabled);
        assertTrue(link.isHeld());
        assertEquals("1", store.get("hold"));                               // 앱이 다시 켜져도 남음
        assertTrue(new DeviceLink(store).isHeld());
        assertFalse(new DeviceLink(store).enabled);
    }

    @Test
    public void heldPhoneStaysOffWhenTheServerSaysOn() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        link.holdForLogout();
        enabled = true;                                                     // 다른 가족이 앱에서 켬
        link.heartbeat(false);
        assertFalse(link.enabled);                                    // 이 휴대폰은 꺼진 채로
        assertFalse(enabled);                                               // 서버에도 다시 '꺼짐'
        assertTrue(link.isHeld());
    }

    @Test
    public void turningOnOnThisPhoneEndsTheHold() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        link.holdForLogout();
        assertNull(link.setEnabled(true));                                  // 이 휴대폰에서 직접 '감지 켜기'
        assertFalse(link.isHeld());
        assertTrue(link.enabled);
        assertTrue(enabled);
        link.heartbeat(true);
        assertTrue(link.enabled);
    }

    @Test
    public void logoutHoldWithoutNetworkIsSentLater() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        down = true;
        assertFalse(link.holdForLogout());                                  // 서버에는 못 알림
        assertFalse(link.enabled);                                    // 그래도 이 휴대폰은 꺼짐
        assertTrue(enabled);
        down = false;
        link.heartbeat(false);                                              // 다음 상태 신호 때
        assertFalse(enabled);                                               // 서버에도 '꺼짐'
        assertFalse(link.enabled);
    }

    @Test
    public void unpairAndForgetRemovesThisPhoneOnlyWithItsOwnToken() {
        MemStore store = new MemStore();
        DeviceLink link = paired(store, new ArrayList<>());
        assertTrue(link.unpairAndForget());
        assertTrue(unpaired);                                               // 서버: 이 기기 토큰으로 자기 기록만 삭제
        assertFalse(link.isPaired());
        assertTrue(store.m.isEmpty());                                      // 이 휴대폰의 연결 정보도 지움
        revoked = false;
        DeviceLink offline = paired(new MemStore(), new ArrayList<>());
        down = true;
        assertFalse(offline.unpairAndForget());                             // 서버에 못 알려도
        assertFalse(offline.isPaired());                                    // 이 휴대폰에서는 지움
    }

    @Test
    public void notPairedPhoneHasNothingToHold() {
        DeviceLink link = new DeviceLink(new MemStore());
        assertFalse(link.holdForLogout());
        assertFalse(link.isPaired());
    }
}
