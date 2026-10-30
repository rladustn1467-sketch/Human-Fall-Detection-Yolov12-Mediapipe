package com.humanfall.app.detect;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Lets the web app (server/app/next, shown in this app) open the device screen. The web app shows its
 * '이 휴대폰으로 감지하기' (settings) and '감지용 휴대전화 연결하기' (below the login screen) entries only when this
 * plugin exists, i.e. only inside this Android app.
 * open({mode, code}): mode "self" = this phone, connected with a code the logged-in web app just got from the server
 * (paired at once, the code is never shown); "dedicated" = a spare phone, the person types the code.
 */
@CapacitorPlugin(name = "Detector")
public class DetectorPlugin extends Plugin {

    /** Origin of the web app this app loads (the same server the device API is on). */
    private String serverOrigin() {
        String url = getBridge().getServerUrl();
        if (url == null || url.isEmpty()) return null;
        Uri u = Uri.parse(url);
        if (u.getScheme() == null || u.getAuthority() == null) return null;
        return u.getScheme() + "://" + u.getAuthority();
    }

    @PluginMethod
    public void open(PluginCall call) {
        Intent i = new Intent(getContext(), DetectorActivity.class);
        String origin = serverOrigin();
        if (origin != null) i.putExtra(DetectorActivity.EXTRA_SERVER, origin);
        String mode = call.getString("mode");
        if (DetectorActivity.MODE_SELF.equals(mode) || DetectorActivity.MODE_DEDICATED.equals(mode)) {
            i.putExtra(DetectorActivity.EXTRA_MODE, mode);
        }
        String code = call.getString("code");
        if (code != null && !code.isEmpty()) i.putExtra(DetectorActivity.EXTRA_CODE, code);
        if (Boolean.TRUE.equals(call.getBoolean("signedIn", false))) i.putExtra(DetectorActivity.EXTRA_SIGNED_IN, true);
        getActivity().startActivity(i);
        call.resolve();
    }

    /**
     * Logout of the web app on this phone. Only when this phone is connected as '이 휴대폰' (self): detection is held
     * off (DeviceLink.holdForLogout, also tells the server), the detection service is stopped and we wait until the
     * camera is really released. A spare phone connected with a code (dedicated) is not touched.
     * Resolves {self, stopped, serverUpdated}.
     */
    @PluginMethod
    public void stopForLogout(PluginCall call) {
        Context ctx = getContext();
        DeviceLink link = DetectorRuntime.link(ctx);
        JSObject o = new JSObject();
        if (!link.isPaired() || !DetectorActivity.MODE_SELF.equals(DetectorActivity.savedMode(ctx))) {
            o.put("self", false);
            call.resolve(o);
            return;
        }
        boolean wasOn = link.enabled;
        new Thread(() -> {
            boolean serverUpdated = link.holdForLogout();
            DetectionService.stop(ctx);
            long end = System.currentTimeMillis() + 5000;
            while (DetectorRuntime.STATE.serviceRunning && System.currentTimeMillis() < end) {
                try {
                    Thread.sleep(100);
                } catch (InterruptedException e) {
                    break;
                }
            }
            boolean stopped = !DetectorRuntime.STATE.serviceRunning && !DetectorRuntime.cameraOk();
            o.put("self", true);
            o.put("wasOn", wasOn);
            o.put("stopped", stopped);
            o.put("serverUpdated", serverUpdated);
            call.resolve(o);
        }, "fd-logout-stop").start();
    }

    /**
     * After the account was withdrawn (only for '이 휴대폰', after stopForLogout): remove this phone's device from the
     * server with its own device token and forget the connection here, so another account can connect this phone
     * again. Spare phones connected with a code are not touched. Resolves {self, removed}.
     */
    @PluginMethod
    public void unpairAfterWithdraw(PluginCall call) {
        Context ctx = getContext();
        DeviceLink link = DetectorRuntime.link(ctx);
        JSObject o = new JSObject();
        if (!link.isPaired() || !DetectorActivity.MODE_SELF.equals(DetectorActivity.savedMode(ctx))) {
            o.put("self", false);
            call.resolve(o);
            return;
        }
        new Thread(() -> {
            DetectionService.stop(ctx);
            boolean removed = link.unpairAndForget();
            o.put("self", true);
            o.put("removed", removed);
            call.resolve(o);
        }, "fd-withdraw-unpair").start();
    }

    @PluginMethod
    public void status(PluginCall call) {
        DeviceLink link = DetectorRuntime.link(getContext());
        JSObject o = new JSObject();
        o.put("paired", link.isPaired());
        o.put("revoked", link.isRevoked());
        o.put("location", link.location());
        o.put("mode", DetectorActivity.savedMode(getContext()));
        o.put("enabled", link.enabled);
        o.put("detecting", DetectorRuntime.cameraOk());
        double fps = DetectorRuntime.STATE.fps;
        if (DetectorRuntime.cameraOk() && !Double.isNaN(fps)) o.put("fps", Math.round(fps * 10) / 10.0);
        o.put("held", link.isHeld());
        call.resolve(o);
    }
}
