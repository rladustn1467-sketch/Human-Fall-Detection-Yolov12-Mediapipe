package com.humanfall.app.detect;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import com.humanfall.app.R;

/**
 * After the phone restarts (or the app is updated) the detection service is gone. Android 15+ does not let an app
 * start a camera service from these broadcasts, so a detecting phone shows a notification instead: tapping it opens
 * the detector screen, which starts detection again (DetectorActivity.onResume). The notification is removed when
 * the service starts. Not shown when the phone is not paired, was revoked, held by logout or turned off on the phone.
 */
public class BootReceiver extends BroadcastReceiver {
    static final String CHANNEL = "detect_stopped";
    static final int NOTIFICATION_ID = 42;

    @Override
    public void onReceive(Context context, Intent intent) {
        String a = intent != null ? intent.getAction() : null;
        if (!Intent.ACTION_BOOT_COMPLETED.equals(a) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) return;
        DeviceLink link = DetectorRuntime.link(context);
        if (!shouldRemind(link.isPaired(), link.isRevoked(), link.isHeld(), link.enabled)) return;
        remind(context);
    }

    /** Remind only phones that were detecting: paired, not revoked, not held by logout, detection on. */
    static boolean shouldRemind(boolean paired, boolean revoked, boolean held, boolean enabled) {
        return paired && !revoked && !held && enabled;
    }

    static void remind(Context context) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, context.getString(R.string.detect_stopped_channel),
                    NotificationManager.IMPORTANCE_HIGH);
            context.getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
        Intent open = new Intent(context, DetectorActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(context, NOTIFICATION_ID, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        NotificationCompat.Builder b = new NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_fall_alert)
                .setContentTitle(context.getString(R.string.detect_stopped_title))
                .setContentText(context.getString(R.string.detect_stopped_text))
                .setStyle(new NotificationCompat.BigTextStyle().bigText(context.getString(R.string.detect_stopped_text)))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_REMINDER)
                .setAutoCancel(true)
                .setContentIntent(pi);
        try {
            NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, b.build());
        } catch (SecurityException e) {
            // 알림 권한이 없음: 보여 줄 수 없음 (가족 앱에는 기기 상태가 '연결 끊김'으로 보임)
        }
    }

    /** Detection is running again: the reminder is no longer needed. */
    static void clear(Context context) {
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID);
    }
}
