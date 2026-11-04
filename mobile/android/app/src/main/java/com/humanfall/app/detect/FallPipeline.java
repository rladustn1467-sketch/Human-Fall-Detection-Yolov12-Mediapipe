package com.humanfall.app.detect;

import android.graphics.Bitmap;
import android.util.Log;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Supplier;

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
    private static final long SETUP_CHECK_MS = 1000;

    /** The photo is optional: an error while making it must not lose the fall, which is then sent without a photo. */
    static byte[] photoOrNull(Supplier<byte[]> render, Consumer<Throwable> onError) {
        try {
            return render.get();
        } catch (RuntimeException | OutOfMemoryError e) {
            onError.accept(e);
            return null;
        }
    }

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
        SetupCheck.Result setup;   // 설치 확인 (감지 화면을 보고 있을 때만)
        byte[] preview;            // 사람을 가린 미리보기 JPEG. 화면에만 보이고 저장·전송하지 않음
    }

    private final PoseDetector detector;
    private final Listener listener;
    private final LegacyFallLogic logic = new LegacyFallLogic();
    private final FrameMath.LowLight lowLight = new FrameMath.LowLight();
    private final Map<Integer, Double> fallenAt = new HashMap<>();
    private final V2Shadow v2;
    private long nextSetupCheckAt;
    /** The person is looking at the detector screen: make the setup check about once a second. */
    volatile boolean setupCheckWanted;

    FallPipeline(PoseDetector detector, Listener listener) {
        this.detector = detector;
        this.listener = listener;
        this.v2 = new V2Shadow();
    }

    /** v2's alarm times in seconds (the clock given to process). Log only. */
    List<Double> v2Alarms() {
        return v2.alarms();
    }

    private void checkSetup(Stats s, Bitmap frame, PoseDetector.Frame pose, PoseBridge.People people, double brightness) {
        int main = -1, largest = -1;
        for (int i = 0; i < people.boxes.size(); i++) {
            int[] b = people.boxes.get(i);
            int area = (b[2] - b[0]) * (b[3] - b[1]);
            if (area > largest) {
                largest = area;
                main = i;
            }
        }
        boolean whole = main >= 0 && SetupCheck.wholeBody(pose.poses.get(people.sources.get(main)));
        s.setup = SetupCheck.of(s.persons, brightness, whole);
        List<float[]> masks = new ArrayList<>();
        for (int src : people.sources) masks.add(src < pose.masks.size() ? pose.masks.get(src) : null);
        if (main < 0 || masks.contains(null)) return;
        s.preview = photoOrNull(() -> Silhouette.render(frame, people.boxes, masks, pose.maskWidth, pose.maskHeight),
                e -> Log.e(TAG, "미리보기 처리 오류", e));
    }

    Stats process(Bitmap camera, long nowMs) {
        Stats s = new Stats();
        Bitmap frame = Silhouette.shrink(camera);   // 분석·사진 모두 긴 변 640 (원본 크기 사본은 만들지 않음)
        try {
            int w = frame.getWidth(), h = frame.getHeight();
            int[] px = new int[w * h];
            frame.getPixels(px, 0, w, 0, 0, w, h);
            boolean checkSetup = setupCheckWanted && nowMs >= nextSetupCheckAt;
            double brightness = checkSetup ? SetupCheck.meanBrightness(px) : 0;   // 밝기 보정 전 값 (방이 어두운지)
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
            if (checkSetup) {
                nextSetupCheckAt = nowMs + SETUP_CHECK_MS;
                checkSetup(s, frame, pose, people, brightness);
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
            final Bitmap shot = frame;
            byte[] jpeg = masks.contains(null) ? null
                    : photoOrNull(() -> Silhouette.render(shot, people.boxes, masks, pose.maskWidth, pose.maskHeight),
                            e -> Log.e(TAG, "실루엣 처리 오류", e));
            if (jpeg == null) Log.w(TAG, "실루엣 처리 실패 - 사진 없이 전송");
            for (int ignored : newIds) listener.onFall(UUID.randomUUID().toString().replace("-", ""), jpeg);
            return s;
        } finally {
            frame.recycle();
        }
    }
}
