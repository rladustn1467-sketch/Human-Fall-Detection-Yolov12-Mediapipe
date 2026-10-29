package com.humanfall.app.detect;

import android.graphics.Bitmap;
import android.util.Log;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * One camera frame → fall decision, in the same order as the PC dashboard:
 * low-light correction → people and poses → fall rule (LegacyFallLogic, same as the PC) → for each newly fallen
 * person (5 s cooldown per person, like the dashboard) one fall event with a silhouette photo.
 * Only frames judged as a fall produce an event; nothing of the frame itself leaves this class.
 * Fall rule v2 runs on the same people next to it, for the log only (V2Shadow): it never sends an event.
 */
final class FallPipeline {
    static final String TAG = "FallPipeline";
    static final double FALL_COOLDOWN_SECONDS = 5.0;   // 대시보드 fall_cooldown 과 같음
    /** Frame rate v2 assumes for the camera (its descent speed counts frames). Not measured on a real phone. */
    static final double CAMERA_FPS_ASSUMED = 30.0;

    interface Listener {
        /** A new fall: its event id (also used for retries) and the silhouette photo (null if it could not be made). */
        void onFall(String eventId, byte[] jpeg);
    }

    static final class Stats {
        int persons;
        boolean fallInFrame;
        int newFalls;
        boolean brightened;
        boolean posture;   // 이 프레임의 자세만 보면 낙상 (이미 알린 사람인지와 상관없이, 비교·기록용)
        double angle = Double.NaN, aspectRatio = Double.NaN;
        V2Shadow.Result v2;   // 기록만 하는 v2 판정 (null = 꺼짐)
    }

    private final PoseDetector detector;
    private final Listener listener;
    private final LegacyFallLogic logic = new LegacyFallLogic();
    private final FrameMath.LowLight lowLight = new FrameMath.LowLight();
    private final Map<Integer, Double> fallenAt = new HashMap<>();
    private final V2Shadow v2;

    FallPipeline(PoseDetector detector, Listener listener, double v2Fps) {
        this.detector = detector;
        this.listener = listener;
        this.v2 = new V2Shadow(v2Fps);
    }

    /** v2's alarm time in seconds (the clock given to process), or null. Log only. */
    Double v2Alarm() {
        return v2.alarm();
    }

    Stats process(Bitmap camera, long nowMs) {
        Stats s = new Stats();
        Bitmap frame = Silhouette.shrink(camera);   // 분석·사진 모두 긴 변 640 (원본 크기 사본은 만들지 않음)
        try {
            int w = frame.getWidth(), h = frame.getHeight();
            int[] px = new int[w * h];
            frame.getPixels(px, 0, w, 0, 0, w, h);
            if (lowLight.process(px)) {
                s.brightened = true;
                Bitmap lit = Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888);
                frame.recycle();
                frame = lit;
            }
            PoseDetector.Frame pose = detector.detect(frame, nowMs);
            PoseBridge.People people = PoseBridge.fromFrame(pose.poses, w, h);
            s.persons = people.boxes.size();
            double now = nowMs / 1000.0;
            LegacyFallLogic.Result r = logic.update(now, people.boxes, people.landmarks);
            s.fallInFrame = r.fallDetected;
            for (PoseFeatures f : r.features) {
                if (f != null) {
                    if (Double.isNaN(s.angle)) {
                        s.angle = f.angle;
                        s.aspectRatio = f.aspectRatio;
                    }
                    if (LegacyFallLogic.isFallPosture(f, LegacyFallLogic.DEFAULT_ANGLE_THRESHOLD)) s.posture = true;
                }
            }
            try {
                s.v2 = v2.update(now, people.boxes, people.landmarks);
                if (s.v2 != null && s.v2.fired) Log.i(TAG, "v2 판정: 낙상 (기록만, 알림은 보내지 않음) t=" + now);
            } catch (RuntimeException e) {
                Log.e(TAG, "v2 판정 오류 - v2 기록을 끔 (지금 방식 감지는 계속)", e);
            }
            if (!r.fallDetected) return s;

            List<Integer> newIds = new ArrayList<>();
            for (int id : r.fallenIds) {
                Double at = fallenAt.get(id);
                if (at == null || now - at > FALL_COOLDOWN_SECONDS) {
                    newIds.add(id);
                    fallenAt.put(id, now);
                }
            }
            if (newIds.isEmpty()) return s;
            s.newFalls = newIds.size();

            List<float[]> masks = new ArrayList<>();
            for (int src : people.sources) masks.add(src < pose.masks.size() ? pose.masks.get(src) : null);
            byte[] jpeg = masks.contains(null) ? null
                    : Silhouette.render(frame, people.boxes, masks, pose.maskWidth, pose.maskHeight);
            if (jpeg == null) Log.w(TAG, "실루엣 처리 실패 - 사진 없이 전송");
            for (int ignored : newIds) listener.onFall(UUID.randomUUID().toString().replace("-", ""), jpeg);
            return s;
        } finally {
            frame.recycle();
        }
    }
}
