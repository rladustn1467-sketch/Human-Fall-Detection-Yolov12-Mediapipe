package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Set;

/**
 * The PC detector's fall decision without YOLO, MediaPipe or drawing: a Java copy of fall_logic/legacy.py
 * (+ rules.py). Same state and decisions as one FallDetector instance, checked against the Python output by
 * FallLogicGoldenTest.
 *
 * A person counts as fallen in a frame when |angle| >= angleThreshold + 10 and aspect ratio < 1.5. A fallen
 * person ID is reported once and again only after its track expired (5 s unseen), like on the PC.
 */
public final class LegacyFallLogic {
    public static final double DEFAULT_ANGLE_THRESHOLD = 45;
    static final double ANGLE_MARGIN = 10;
    static final double MAX_ASPECT_RATIO = 1.5;
    /** 원본에서 낙상 유형 분류는 쓰이지 않아 언제나 이 유형 */
    public static final String DEFAULT_FALL_TYPE = "slip_and_fall";

    public static final class Result {
        public boolean fallsDetected;
        public boolean fallDetected;
        public String fallType;
        public int personCount;
        public final List<Integer> personIds = new ArrayList<>();
        public final List<Integer> fallenIds = new ArrayList<>();
        public final List<PoseFeatures> features = new ArrayList<>();
    }

    private final double angleThreshold;
    private final IouTracker tracker = new IouTracker();
    private final List<PoseFeatures> prevPoses = new ArrayList<>();   // 모든 사람이 같이 쓰는 자세 기록 (원본과 동일)
    private final Set<Integer> fallenPersonIds = new HashSet<>();

    public LegacyFallLogic() {
        this(DEFAULT_ANGLE_THRESHOLD);
    }

    public LegacyFallLogic(double angleThreshold) {
        this.angleThreshold = angleThreshold;
    }

    static boolean isFallPosture(PoseFeatures f, double angleThreshold) {
        return Math.abs(f.angle) >= angleThreshold + ANGLE_MARGIN && f.aspectRatio < MAX_ASPECT_RATIO;
    }

    /**
     * One frame.
     *
     * @param now       seconds (the time the PC would read with time.time())
     * @param boxes     person boxes in frame pixels [x1, y1, x2, y2]
     * @param landmarks one entry per box: crop-normalized landmarks, null (no pose) or empty
     */
    public Result update(double now, List<int[]> boxes, List<double[][]> landmarks) {
        if (landmarks.size() != boxes.size()) throw new IllegalArgumentException("one landmarks entry per box");
        IouTracker.Result tr = tracker.update(boxes, now);
        for (int id : tr.expired) fallenPersonIds.remove(id);

        Result r = new Result();
        r.personCount = boxes.size();
        r.personIds.addAll(tr.boxToId.values());

        LinkedHashMap<Integer, Integer> ids = tr.boxToId;
        List<PoseFeatures> perBox = new ArrayList<>();
        for (int i = 0; i < boxes.size(); i++) {
            double[][] lm = landmarks.get(i);
            perBox.add(lm == null ? null : PoseFeatures.compute(lm, prevPoses, now));
        }
        r.features.addAll(perBox);

        for (int i = 0; i < boxes.size(); i++) {
            Integer personId = ids.get(i);
            if (personId != null && fallenPersonIds.contains(personId)) continue;
            double[][] lm = landmarks.get(i);
            PoseFeatures f = perBox.get(i);
            if (lm == null || lm.length == 0 || f == null) continue;
            if (isFallPosture(f, angleThreshold)) {
                if (personId != null && !r.fallenIds.contains(personId)) {
                    r.fallenIds.add(personId);
                    fallenPersonIds.add(personId);
                }
                r.fallDetected = true;
                r.fallType = DEFAULT_FALL_TYPE;
                r.fallsDetected = true;
            }
        }
        return r;
    }
}
