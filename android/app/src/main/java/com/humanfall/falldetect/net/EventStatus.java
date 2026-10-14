package com.humanfall.falldetect.net;

import org.json.JSONObject;

/**
 * One fall event as the server returns it (GET /api/events/{id}, POST .../response).
 * Field names follow server/main.py _public(); only the ones the app uses are kept.
 */
public final class EventStatus {
    public static final String AWAITING_RESPONSE = "awaiting_response";
    public static final String TIMEOUT = "timeout";
    public static final String SAFE = "safe";
    public static final String HELP_NEEDED = "help_needed";

    public final String eventId;
    public final String status;
    /** 서버가 붙인 한글 상태 이름 (예: "응답 대기", "시간 초과 후 안전 확인") */
    public final String statusLabel;
    /** 응답 마감까지 남은 초 (응답 대기 중이 아니면 0) */
    public final int remainingSeconds;
    /** 자동 119 신고(시뮬레이션)까지 남은 초, 예정이 없으면 null */
    public final Integer reportInSeconds;
    /** 119 신고(시뮬레이션)를 이미 했는지 */
    public final boolean reported;
    public final boolean isTest;
    public final boolean lateResponse;
    public final String deviceId;

    private EventStatus(JSONObject json) {
        eventId = json.optString("event_id", "");
        status = json.optString("status", "");
        statusLabel = json.optString("status_label", status);
        remainingSeconds = json.optInt("remaining_seconds", 0);
        reportInSeconds = json.isNull("report_in_seconds") ? null : json.optInt("report_in_seconds");
        JSONObject escalation = json.optJSONObject("escalation");
        reported = escalation != null && !escalation.isNull("report") && escalation.has("report");
        isTest = json.optBoolean("is_test", false);
        lateResponse = json.optBoolean("late_response", false);
        deviceId = json.optString("device_id", "");
    }

    /** Parses a server event; throws BAD_RESPONSE when the required fields are missing. */
    public static EventStatus fromJson(JSONObject json) throws ApiException {
        if (json == null || json.optString("event_id", "").isEmpty() || json.optString("status", "").isEmpty()) {
            throw new ApiException(ApiException.Kind.BAD_RESPONSE, 0, "서버 응답을 이해할 수 없어요.");
        }
        return new EventStatus(json);
    }
}
