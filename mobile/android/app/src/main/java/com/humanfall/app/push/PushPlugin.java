package com.humanfall.app.push;

import android.Manifest;
import android.content.Intent;
import android.os.Build;
import android.provider.Settings;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.google.firebase.messaging.FirebaseMessaging;

/**
 * Lets the web app (server/app/next, js/push.js) use fall-alert pushes on this phone: notification permission and
 * channel state, the FCM token (sent to the server by the web app, tied to the login), opening Android's
 * notification settings, and the incident to open when the app was started from a notification.
 * Events: incidentOpened {incidentId} (notification tapped while the app runs), received {incidentId} (a push
 * arrived while the app is on screen: refresh now), tokenChanged.
 */
@CapacitorPlugin(name = "Push",
        permissions = @Permission(strings = {Manifest.permission.POST_NOTIFICATIONS}, alias = "notifications"))
public class PushPlugin extends Plugin {
    private static volatile PushPlugin instance;
    private String pendingIncident;   // 알림을 눌러 앱을 처음 연 경우의 사고 id (웹앱이 한 번 가져감)

    @Override
    public void load() {
        instance = this;
        PushChannels.ensure(getContext());
        Intent start = getActivity() != null ? getActivity().getIntent() : null;
        if (start != null) pendingIncident = start.getStringExtra(PushService.EXTRA_INCIDENT);
    }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        super.handleOnNewIntent(intent);
        String id = intent.getStringExtra(PushService.EXTRA_INCIDENT);
        if (id == null) return;
        pendingIncident = id;
        JSObject o = new JSObject();
        o.put("incidentId", id);
        notifyListeners("incidentOpened", o);
    }

    static void received(String incidentId) {
        PushPlugin p = instance;
        if (p == null) return;
        JSObject o = new JSObject();
        o.put("incidentId", incidentId);
        p.notifyListeners("received", o);
    }

    static void tokenChanged(String token) {
        PushPlugin p = instance;
        if (p != null) p.notifyListeners("tokenChanged", new JSObject());   // 토큰 값은 이벤트로 보내지 않음 (getToken 으로)
    }

    private String permission() {
        if (Build.VERSION.SDK_INT < 33) return "granted";   // 안드로이드 12 이하는 설치할 때 허용됨 (설정에서 끌 수는 있음)
        PermissionState s = getPermissionState("notifications");
        if (s == PermissionState.GRANTED) return "granted";
        return s == PermissionState.PROMPT ? "prompt" : "denied";   // 한 번이라도 거부함(PROMPT_WITH_RATIONALE 포함): 설정으로 안내
    }

    private JSObject statusObject() {
        JSObject o = new JSObject();
        o.put("permission", permission());
        o.put("blocked", PushChannels.blocked(getContext()));   // 앱 알림 또는 낙상 알림 채널이 꺼짐
        return o;
    }

    @PluginMethod
    public void status(PluginCall call) {
        call.resolve(statusObject());
    }

    @PluginMethod
    public void requestPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < 33 || "granted".equals(permission())) {
            call.resolve(statusObject());
            return;
        }
        requestPermissionForAlias("notifications", call, "permissionAnswered");
    }

    @PermissionCallback
    private void permissionAnswered(PluginCall call) {
        call.resolve(statusObject());
    }

    @PluginMethod
    public void getToken(PluginCall call) {
        FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
            if (!task.isSuccessful() || task.getResult() == null) {
                call.reject("알림 토큰을 받지 못했어요");
                return;
            }
            JSObject o = new JSObject();
            o.put("token", task.getResult());
            call.resolve(o);
        });
    }

    @PluginMethod
    public void openSettings(PluginCall call) {
        Intent i;
        android.app.NotificationManager nm = getContext().getSystemService(android.app.NotificationManager.class);
        boolean appOn = nm != null && nm.areNotificationsEnabled();
        if (Build.VERSION.SDK_INT >= 26 && appOn && PushChannels.blocked(getContext())) {   // 낙상 알림 채널만 꺼짐
            i = new Intent(Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName())
                    .putExtra(Settings.EXTRA_CHANNEL_ID, PushChannels.FALL_ALERT);
        } else {
            i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        }
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        call.resolve();
    }

    /** The incident to open because the app was started from a notification (once). */
    @PluginMethod
    public void takeOpenedIncident(PluginCall call) {
        JSObject o = new JSObject();
        o.put("incidentId", pendingIncident);
        pendingIncident = null;
        call.resolve(o);
    }
}
