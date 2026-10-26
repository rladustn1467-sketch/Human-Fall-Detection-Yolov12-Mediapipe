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
        public volatile long frames;
        public volatile int persons;
        public volatile long lastFallAt;
        public volatile String lastFallResult;
    }

    public static final State STATE = new State();

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
        String c = STATE.camera;
        return ("running".equals(c) || "mock".equals(c)) && System.currentTimeMillis() - STATE.lastFrameAt < 5000;
    }

    private DetectorRuntime() {
    }
}
