package com.humanfall.falldetect.net;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Server address, access token and device id, saved on the device only (never in the code,
 * the repository or logs). Entered on the settings screen.
 */
public final class ServerConfig {
    /** 에뮬레이터에서 PC의 localhost 는 10.0.2.2 (실제 서버 포트 8000) */
    public static final String DEFAULT_SERVER_URL = "http://10.0.2.2:8000";
    public static final String DEFAULT_DEVICE_ID = "android-emulator";

    private static final String PREFS = "server_config";
    private static final String KEY_URL = "server_url";
    private static final String KEY_TOKEN = "access_token";
    private static final String KEY_DEVICE = "device_id";

    public final String serverUrl;
    public final String token;
    public final String deviceId;

    public ServerConfig(String serverUrl, String token, String deviceId) {
        this.serverUrl = serverUrl == null ? "" : serverUrl.trim();
        this.token = token == null ? "" : token.trim();
        String device = deviceId == null ? "" : deviceId.trim();
        this.deviceId = device.isEmpty() ? DEFAULT_DEVICE_ID : device;
    }

    public static ServerConfig load(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        return new ServerConfig(prefs.getString(KEY_URL, DEFAULT_SERVER_URL),
                prefs.getString(KEY_TOKEN, ""),
                prefs.getString(KEY_DEVICE, DEFAULT_DEVICE_ID));
    }

    public void save(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_URL, serverUrl)
                .putString(KEY_TOKEN, token)
                .putString(KEY_DEVICE, deviceId)
                .apply();
    }

    public boolean isComplete() {
        return !serverUrl.isEmpty() && !token.isEmpty();
    }

    public EventApi api() {
        return new EventApi(serverUrl, token);
    }
}
