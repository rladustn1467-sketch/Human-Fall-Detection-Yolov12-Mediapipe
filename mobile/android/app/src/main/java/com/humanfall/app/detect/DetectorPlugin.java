package com.humanfall.app.detect;

import android.content.Intent;
import android.net.Uri;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Lets the web app (server/app/next, shown in this app) open the device screen. The web app shows its
 * '이 휴대폰으로 감지하기' (settings) and '안 쓰는 휴대폰을 감지 기기로 쓰기' (first screen) entries only when this
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
        getActivity().startActivity(i);
        call.resolve();
    }

    @PluginMethod
    public void status(PluginCall call) {
        DeviceLink link = DetectorRuntime.link(getContext());
        JSObject o = new JSObject();
        o.put("paired", link.isPaired());
        o.put("revoked", link.isRevoked());
        o.put("location", link.location());
        o.put("mode", DetectorActivity.savedMode(getContext()));
        o.put("enabled", link.serverEnabled);
        o.put("detecting", DetectorRuntime.cameraOk());
        call.resolve(o);
    }
}
