package com.humanfall.falldetect.events;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import com.humanfall.falldetect.net.ApiException;
import com.humanfall.falldetect.net.EventApi;
import com.humanfall.falldetect.net.ServerConfig;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The single place where "a fall happened" is turned into a server event.
 * Today the test button calls it; later the on-device fall detection will call the same method,
 * so screens and server code do not change when detection is added.
 */
public final class FallReporter {
    /** PC 대시보드의 테스트 낙상(F9)과 같은 유형 */
    public static final String TEST_FALL_TYPE = "slip_and_fall";

    public interface Callback {
        void onSent(String eventId);

        void onFailed(ApiException error);
    }

    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private FallReporter() {
    }

    /** Sends one fall event in the background; the callback runs on the main thread. */
    public static void report(Context context, String fallType, boolean isTest, Callback callback) {
        ServerConfig config = ServerConfig.load(context.getApplicationContext());
        EXECUTOR.execute(() -> {
            try {
                String eventId = config.api().sendEvent(EventApi.newEventId(), config.deviceId, fallType, isTest);
                MAIN.post(() -> callback.onSent(eventId));
            } catch (ApiException e) {
                MAIN.post(() -> callback.onFailed(e));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
    }
}
