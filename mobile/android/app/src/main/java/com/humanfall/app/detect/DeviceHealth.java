package com.humanfall.app.detect;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;
import android.os.PowerManager;

/** This phone's battery and heat, for the status signal and the detector screen. */
final class DeviceHealth {
    private DeviceHealth() {
    }

    static DeviceLink.Health read(Context context) {
        DeviceLink.Health h = new DeviceLink.Health();
        Intent battery = context.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (battery != null) {
            int level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            if (level >= 0 && scale > 0) h.battery = level * 100 / scale;
            h.charging = battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0;
        }
        if (Build.VERSION.SDK_INT >= 29) {
            PowerManager power = context.getSystemService(PowerManager.class);
            h.hot = power != null && power.getCurrentThermalStatus() >= PowerManager.THERMAL_STATUS_SEVERE;
        }
        return h;
    }
}
