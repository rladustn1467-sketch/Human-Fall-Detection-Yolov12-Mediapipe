package com.humanfall.falldetect.net;

/** A server call that failed, with a short Korean message that can be shown to the user as is. */
public class ApiException extends Exception {
    public enum Kind {
        /** 토큰이 틀림 (HTTP 401) - 다시 보내도 같으므로 재시도하지 않음 */
        AUTH,
        /** 낙상 기록이 없음 (HTTP 404) */
        NOT_FOUND,
        /** 서버가 요청을 거절 (그 밖의 4xx) */
        REJECTED,
        /** 서버 내부 오류 (5xx) */
        SERVER,
        /** 연결 실패, 시간 초과 */
        NETWORK,
        /** 서버 응답을 해석할 수 없음 */
        BAD_RESPONSE,
        /** 서버 주소나 토큰이 설정되지 않음 */
        NOT_CONFIGURED
    }

    public final Kind kind;
    public final int httpCode;

    public ApiException(Kind kind, int httpCode, String message, Throwable cause) {
        super(message, cause);
        this.kind = kind;
        this.httpCode = httpCode;
    }

    public ApiException(Kind kind, int httpCode, String message) {
        this(kind, httpCode, message, null);
    }

    /** True for failures that may succeed if sent again (server down, network, 5xx). */
    public boolean isRetryable() {
        return kind == Kind.NETWORK || kind == Kind.SERVER;
    }
}
