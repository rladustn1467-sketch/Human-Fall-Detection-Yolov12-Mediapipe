package com.humanfall.app.detect;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.Map;

/**
 * One DeviceLink per app (token in app-private SharedPreferences; the app's allowBackup is off, so it is not copied
 * by Android backups) and the detection state shown on the device screen.
 */
public final class DetectorRuntime {
    private static DeviceLink link;

    /** What the device screen shows. Written by DetectionService, read by DetectorActivity. */
    public static final class State {
        public volatile boolean serviceRunning;
        /** none, starting, running, mock, permission, error, off */
        public volatile String camera = "none";
        public volatile String cameraError;
        public volatile long lastFrameAt;
        /** 프레임 분석이 마지막으로 끝난 시각 (카메라가 켜진 뒤 첫 프레임 시각부터 셈) */
        public volatile long lastAnalyzedAt;
        /** 카메라나 분석이 멈춰 자동으로 다시 시작하는 중 (CameraWatchdog) */
        public volatile boolean recovering;
        /** 감지 화면을 보고 있음: 그동안만 설치 확인을 만듦 */
        public volatile boolean setupCheckWanted;
        public volatile SetupCheck.Result setup;
        /** 사람을 가린 미리보기 (메모리에만, 저장·전송 안 함) */
        public volatile byte[] preview;
        public volatile long frames;
        public volatile int persons;
        public volatile long lastFallAt;
        public volatile String lastFallResult;
        /** 최근 10초 동안 1초에 분석한 프레임 수, 프레임당 분석 시간 (ms), 카메라 프레임 크기 (NaN/null = 아직 모름) */
        public volatile double fps = Double.NaN;
        public volatile double frameMs = Double.NaN;
        public volatile String frameSize;
    }

    public static final State STATE = new State();
    private static final long STALL_MS = 5000;

    public static synchronized DeviceLink link(Context context) {
        if (link == null) {
            SharedPreferences prefs = context.getApplicationContext().getSharedPreferences("fd_device_link", Context.MODE_PRIVATE);
            link = new DeviceLink(new DeviceLink.Store() {
                public String get(String key) {
                    return prefs.getString(key, null);
                }

                public void putAll(Map<String, String> values) {
                    SharedPreferences.Editor e = prefs.edit();
                    for (Map.Entry<String, String> v : values.entrySet()) e.putString(v.getKey(), v.getValue());
                    e.commit();   // 앱이 바로 꺼져도 토큰·해제 표시가 남도록 바로 저장
                }

                public void clear() {
                    prefs.edit().clear().commit();
                }
            });
        }
        return link;
    }

    /** The camera delivered a frame in the last few seconds (sent with the status signal). */
    public static boolean cameraOk() {
        return running() && System.currentTimeMillis() - STATE.lastFrameAt < STALL_MS && !analysisFailing();
    }

    /** Frames keep coming but none could be analysed for a while: no fall can be detected. */
    public static boolean analysisFailing() {
        return analysisFailing(STATE.lastFrameAt, STATE.lastAnalyzedAt);
    }

    static boolean analysisFailing(long lastFrameAt, long lastAnalyzedAt) {
        return lastFrameAt - lastAnalyzedAt >= STALL_MS;
    }

    /** The camera delivered frames earlier but stopped (for example another app took it). */
    public static boolean cameraStalled() {
        return running() && cameraStalled(STATE.lastFrameAt, System.currentTimeMillis());
    }

    static boolean cameraStalled(long lastFrameAt, long now) {
        return lastFrameAt > 0 && now - lastFrameAt >= STALL_MS;
    }

    private static boolean running() {
        String c = STATE.camera;
        return "running".equals(c) || "mock".equals(c);
    }

    private DetectorRuntime() {
    }
}
