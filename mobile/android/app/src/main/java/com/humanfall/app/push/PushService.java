package com.humanfall.app.push;

import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;
import com.humanfall.app.MainActivity;
import com.humanfall.app.R;
import java.util.Map;

/**
 * Fall-alert pushes (Firebase Cloud Messaging).
 * App in the background or closed: Android shows the server's notification itself (channel fall_alert) and
 * opens the app with the extra incidentId when it is tapped; this service is not called.
 * App on screen: this service is called; no system notification is shown (the app already shows the
 * emergency screen), the web app is only told to refresh at once. A data-only message while not on screen is
 * shown here the same way as the server's notification.
 */
public class PushService extends FirebaseMessagingService {
    public static final String EXTRA_INCIDENT = "incidentId";

    @Override
    public void onNewToken(@NonNull String token) {
        PushPlugin.tokenChanged(token);   // 다음에 앱이 열려 있으면 웹앱이 서버에 다시 등록
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage msg) {
        Map<String, String> data = msg.getData();
        String incidentId = data.get(EXTRA_INCIDENT);
        if (AppVisibility.onScreen()) {
            PushPlugin.received(incidentId);   // 화면에 떠 있으면 앱의 긴급 화면으로 충분 (같은 알림을 두 번 보이지 않음)
            return;
        }
        RemoteMessage.Notification n = msg.getNotification();
        show(this, incidentId, n != null && n.getTitle() != null ? n.getTitle() : "낙상 지킴이",
                n != null && n.getBody() != null ? n.getBody() : "낙상 사고가 감지됐어요. 확인해 주세요.");
    }

    static void show(Context context, String incidentId, String title, String body) {
        PushChannels.ensure(context);
        Intent open = new Intent(context, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (incidentId != null) open.putExtra(EXTRA_INCIDENT, incidentId);
        PendingIntent pi = PendingIntent.getActivity(context, incidentId == null ? 0 : incidentId.hashCode(), open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder b = new NotificationCompat.Builder(context, PushChannels.FALL_ALERT)
                .setSmallIcon(R.drawable.ic_stat_fall_alert)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setAutoCancel(true)
                .setContentIntent(pi);
        NotificationManager nm = context.getSystemService(NotificationManager.class);
        if (nm != null && nm.areNotificationsEnabled()) nm.notify(incidentId == null ? "fall" : incidentId, 1, b.build());
    }
}
