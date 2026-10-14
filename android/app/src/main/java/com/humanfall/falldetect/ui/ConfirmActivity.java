package com.humanfall.falldetect.ui;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

import com.humanfall.falldetect.R;
import com.humanfall.falldetect.net.ApiException;
import com.humanfall.falldetect.net.EventApi;
import com.humanfall.falldetect.net.EventStatus;
import com.humanfall.falldetect.net.ServerConfig;

import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The person's answer to one fall: "괜찮아요" / "도움이 필요해요".
 *
 * The server stays the only judge of deadlines, alerts and the 119 (simulation) flow: this screen
 * shows the state the server reports for this event id (GET every 3 s, like the /app page) and
 * sends the answer with POST /api/events/{id}/response. States and wording follow
 * server/app/js/screens/self.js.
 */
public class ConfirmActivity extends Activity {
    public static final String EXTRA_EVENT_ID = "event_id";
    /** /app 의 config.js pollIntervalSeconds 와 같은 간격 */
    private static final long POLL_INTERVAL_MS = 3000;
    private static final long TICK_MS = 1000;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private EventApi api;
    private String eventId;
    private EventStatus latest;
    private long receivedAt;      // latest 를 받은 시각 (남은 시간 계산용)
    private boolean polling;
    private boolean pollInFlight;
    private boolean sending;

    private TextView badge;
    private TextView question;
    private TextView detail;
    private TextView notice;
    private TextView serverState;
    private Button primary;
    private Button secondary;

    private final Runnable pollTask = new Runnable() {
        @Override
        public void run() {
            poll();
            if (polling) {
                main.postDelayed(this, POLL_INTERVAL_MS);
            }
        }
    };

    private final Runnable tickTask = new Runnable() {
        @Override
        public void run() {
            updateCountdown();
            if (polling) {
                main.postDelayed(this, TICK_MS);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_confirm);
        badge = findViewById(R.id.test_badge);
        question = findViewById(R.id.question);
        detail = findViewById(R.id.detail);
        notice = findViewById(R.id.notice);
        serverState = findViewById(R.id.server_state);
        primary = findViewById(R.id.primary_button);
        secondary = findViewById(R.id.secondary_button);

        eventId = getIntent().getStringExtra(EXTRA_EVENT_ID);
        if (eventId == null || eventId.isEmpty()) {
            finish();
            return;
        }
        api = ServerConfig.load(this).api();
        question.setText("서버에서 상태를 확인하는 중이에요...");
        primary.setVisibility(View.GONE);
        secondary.setVisibility(View.GONE);
    }

    @Override
    protected void onResume() {
        super.onResume();
        polling = true;
        main.post(pollTask);
        main.post(tickTask);
    }

    @Override
    protected void onPause() {
        super.onPause();
        polling = false;
        main.removeCallbacks(pollTask);
        main.removeCallbacks(tickTask);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdownNow();
    }

    private void poll() {
        if (pollInFlight || sending) {
            return;
        }
        pollInFlight = true;
        executor.execute(() -> {
            EventStatus status = null;
            ApiException error = null;
            try {
                status = api.getEvent(eventId);
            } catch (ApiException e) {
                error = e;
            }
            EventStatus s = status;
            ApiException err = error;
            main.post(() -> {
                pollInFlight = false;
                if (isDestroyed()) {
                    return;
                }
                if (err != null) {
                    // 연결이 잠시 끊겨도 마지막으로 받은 상태는 그대로 보여 줌
                    showNotice(err.getMessage() + " 다시 확인하고 있어요.");
                } else if (!sending) {
                    showNotice(null);
                    show(s);
                }
            });
        });
    }

    private void answer(String response) {
        if (sending) {
            return;
        }
        sending = true;
        primary.setEnabled(false);
        secondary.setEnabled(false);
        showNotice("보내는 중이에요...");
        executor.execute(() -> {
            EventStatus status = null;
            ApiException error = null;
            try {
                status = api.respond(eventId, response);
            } catch (ApiException e) {
                error = e;
            }
            EventStatus s = status;
            ApiException err = error;
            main.post(() -> {
                sending = false;
                if (isDestroyed()) {
                    return;
                }
                primary.setEnabled(true);
                secondary.setEnabled(true);
                if (err != null) {
                    showNotice("보내지 못했어요. 한 번 더 눌러 주세요. (" + err.getMessage() + ")");
                } else {
                    showNotice(null);
                    show(s);
                }
            });
        });
    }

    /** Draws the screen for the server state (same four states as the /app self screen). */
    private void show(EventStatus status) {
        latest = status;
        receivedAt = SystemClock.elapsedRealtime();
        badge.setVisibility(status.isTest ? View.VISIBLE : View.GONE);
        serverState.setText(String.format(Locale.ROOT, "서버 상태: %s · 기록 %s · 기기 %s",
                status.statusLabel, shortId(status.eventId), status.deviceId));

        switch (status.status) {
            case EventStatus.AWAITING_RESPONSE:
            case EventStatus.TIMEOUT:
                question.setText("넘어지셨나요?\n괜찮으세요?");
                setButton(primary, "괜찮아요", R.color.safe, EventApi.RESPONSE_SAFE);
                setButton(secondary, "도움이 필요해요", R.color.help, EventApi.RESPONSE_HELP);
                break;
            case EventStatus.HELP_NEEDED:
                question.setText("도움 요청을 보냈어요");
                setButton(primary, "괜찮아졌어요", R.color.safe, EventApi.RESPONSE_SAFE);
                secondary.setVisibility(View.GONE);
                break;
            case EventStatus.SAFE:
                question.setText("괜찮다고 전했어요");
                setButton(primary, "다시 도움이 필요해요", R.color.help, EventApi.RESPONSE_HELP);
                secondary.setVisibility(View.VISIBLE);
                secondary.setText("닫기");
                secondary.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.muted_text)));
                secondary.setOnClickListener(v -> finish());
                break;
            default:
                question.setText("서버 상태: " + status.statusLabel);
                primary.setVisibility(View.GONE);
                secondary.setVisibility(View.GONE);
                break;
        }
        updateCountdown();
    }

    private void setButton(Button button, String text, int colorRes, String response) {
        button.setVisibility(View.VISIBLE);
        button.setText(text);
        button.setBackgroundTintList(ColorStateList.valueOf(getColor(colorRes)));
        button.setOnClickListener(v -> answer(response));
    }

    /** Updates the remaining-time text every second from the last server values. */
    private void updateCountdown() {
        if (latest == null) {
            return;
        }
        long elapsed = (SystemClock.elapsedRealtime() - receivedAt) / 1000;
        String report = latest.reported
                ? "119 신고(시뮬레이션)를 했어요. 실제 119에는 연락하지 않았어요."
                : latest.reportInSeconds == null ? ""
                : String.format(Locale.ROOT, "%d초 뒤 119에 신고해요 (시뮬레이션). 괜찮으면 '괜찮아요'를 누르세요.",
                Math.max(0, latest.reportInSeconds - elapsed));
        switch (latest.status) {
            case EventStatus.AWAITING_RESPONSE:
                detail.setText(String.format(Locale.ROOT, "%d초 안에 눌러 주세요",
                        Math.max(0, latest.remainingSeconds - elapsed)));
                break;
            case EventStatus.TIMEOUT:
                detail.setText(join("응답이 없어서 보호자에게 알렸어요. 지금이라도 눌러 주세요.", report));
                break;
            case EventStatus.HELP_NEEDED:
                detail.setText(join("보호자에게 알렸어요. 움직이지 말고 기다려 주세요.", report));
                break;
            case EventStatus.SAFE:
                detail.setText(latest.reported
                        ? "이미 119 신고(시뮬레이션)가 된 뒤라 보호자에게 신고 취소를 요청했어요."
                        : "보호자에게 알렸어요.");
                break;
            default:
                detail.setText("");
                break;
        }
    }

    private void showNotice(String text) {
        notice.setVisibility(text == null ? View.GONE : View.VISIBLE);
        notice.setText(text == null ? "" : text);
    }

    private static String join(String first, String second) {
        return second.isEmpty() ? first : first + "\n" + second;
    }

    private static String shortId(String id) {
        return id.length() > 8 ? id.substring(0, 8) : id;
    }
}
