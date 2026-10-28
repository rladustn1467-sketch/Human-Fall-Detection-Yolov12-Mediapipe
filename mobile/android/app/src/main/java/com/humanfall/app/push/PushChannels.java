package com.humanfall.app.push;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;

/**
 * Notification channel of fall alerts (same id as the server's push.CHANNEL_ID). High importance (sound,
 * vibration, heads-up), shown on the lock screen with the minimal text the server sends. The person can still
 * change or turn off the channel in Android's settings; this app never overrides that.
 */
public final class PushChannels {
    public static final String FALL_ALERT = "fall_alert";

    private PushChannels() {
    }

    public static void ensure(Context context) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = context.getSystemService(NotificationManager.class);
        if (nm == null || nm.getNotificationChannel(FALL_ALERT) != null) return;   // 이미 있으면 사용자가 바꾼 설정 유지
        NotificationChannel ch = new NotificationChannel(FALL_ALERT, "낙상 사고 알림", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("가족 그룹의 집에서 낙상이 감지되면 알려요");
        ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);   // 잠금 화면 문구에는 이름·주소가 없음
        ch.enableVibration(true);
        ch.setVibrationPattern(new long[]{0, 600, 300, 600, 300, 600});
        ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        ch.setShowBadge(true);
        nm.createNotificationChannel(ch);
    }

    /** True when the person turned this channel off (or all notifications of the app). */
    public static boolean blocked(Context context) {
        NotificationManager nm = context.getSystemService(NotificationManager.class);
        if (nm == null || !nm.areNotificationsEnabled()) return true;
        if (Build.VERSION.SDK_INT < 26) return false;
        NotificationChannel ch = nm.getNotificationChannel(FALL_ALERT);
        return ch != null && ch.getImportance() == NotificationManager.IMPORTANCE_NONE;
    }
}
