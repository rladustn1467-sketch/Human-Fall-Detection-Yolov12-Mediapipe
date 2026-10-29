package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.List;

/**
 * Per-frame inputs of fall rule v2 (FallRuleV2), a Java copy of the parts of tools/urfall_features.py the rule
 * uses: the main person's body line angle (A1), head height above the ankles (H3), box ratio (B1) and downward
 * hip speed (C1), all measured in frame pixels. Checked against the Python output by FallRuleV2GoldenTest.
 *
 * Input per frame: PoseBridge's boxes (frame pixels) and landmarks (fractions of each box, [33][x, y, z, vis]).
 * A joint counts when its visibility is at least 0.5. The main person is the one whose visible joints span the
 * largest area (at least 5 joints); a phantom second person is left out that way.
 * C1 compares the main person's hip with the main person of the frame closest in time to 0.25 s before (ties: the
 * earlier frame; none within 0.1 s, or less than 0.25 s since the first frame: no speed) and divides by the real
 * time between the two frames, because the phone camera drops frames it cannot keep up with (KEEP_ONLY_LATEST).
 * With a steady rate this is the same as counting round(0.25 * fps) frames (tools/urfall_features.py timing="time").
 */
public final class V2Features {
    static final double VIS_MIN = 0.5;
    static final int NOSE = 0, L_SH = 11, R_SH = 12, L_HIP = 23, R_HIP = 24, L_ANK = 27, R_ANK = 28;
    static final int MIN_JOINTS_FOR_EXTENT = 5;
    static final double DESCENT_SECONDS = 0.25;
    static final double DESCENT_TOLERANCE = 0.1;   // 찾는 시각에서 이만큼 넘게 떨어진 프레임뿐이면 속도 없음
    static final double TIME_TIE = 1e-9;           // 이 차이 안의 두 프레임은 같은 거리로 보고 더 이른 쪽

    /** The rule's inputs for one frame; null = not available. */
    public static final class Frame {
        public final Double a1, h3, b1, c1;

        Frame(Double a1, Double h3, Double b1, Double c1) {
            this.a1 = a1;
            this.h3 = h3;
            this.b1 = b1;
            this.c1 = c1;
        }

        static final Frame NOBODY = new Frame(null, null, null, null);
    }

    /** One person's values that need no history. */
    static final class Person {
        Double a1, h3, b1, torso;
        double[] hip;
        double extentArea;
    }

    private final List<Double> times = new ArrayList<>();
    private final List<Person> mains = new ArrayList<>();   // 최근 프레임마다 주 인물 (없으면 null)
    private Double firstTime;

    private static boolean visible(double[][] p, int i) {
        return p[i][2] >= VIS_MIN;
    }

    /** Midpoint of the visible ones of joints a and b (one visible: that joint; none: null). */
    private static double[] midpoint(double[][] p, int a, int b) {
        double x = 0, y = 0;
        int n = 0;
        for (int i : new int[]{a, b}) {
            if (visible(p, i)) {
                x += p[i][0];
                y += p[i][1];
                n++;
            }
        }
        return n == 0 ? null : new double[]{x / n, y / n};
    }

    /** Angle of the line p-q against the horizontal, 0..90 degrees. */
    private static Double lineAngle(double[] p, double[] q) {
        if (p == null || q == null) return null;
        double dx = Math.abs(q[0] - p[0]), dy = Math.abs(q[1] - p[1]);
        if (dx == 0 && dy == 0) return null;
        return Math.toDegrees(Math.atan2(dy, dx));
    }

    /** Box-relative landmarks → frame pixels [x, y, visibility]. */
    static double[][] toPixels(int[] box, double[][] lms) {
        double w = box[2] - box[0], h = box[3] - box[1];
        double[][] out = new double[lms.length][3];
        for (int i = 0; i < lms.length; i++) {
            out[i][0] = box[0] + lms[i][0] * w;
            out[i][1] = box[1] + lms[i][1] * h;
            out[i][2] = lms[i][3];
        }
        return out;
    }

    static Person person(int[] box, double[][] lms) {
        double[][] p = toPixels(box, lms);
        double[] sh = midpoint(p, L_SH, R_SH), hip = midpoint(p, L_HIP, R_HIP), ank = midpoint(p, L_ANK, R_ANK);
        double[] nose = visible(p, NOSE) ? new double[]{p[NOSE][0], p[NOSE][1]} : null;
        Person o = new Person();
        if (sh != null && hip != null) {
            double t = Math.hypot(hip[0] - sh[0], hip[1] - sh[1]);
            o.torso = t < 1.0 ? null : t;                      // 몸통이 한 점으로 겹침: 잣대로 쓸 수 없음
        }
        double minX = Double.MAX_VALUE, maxX = -Double.MAX_VALUE, minY = Double.MAX_VALUE, maxY = -Double.MAX_VALUE;
        int n = 0;
        for (double[] q : p) {
            if (q[2] >= VIS_MIN) {
                minX = Math.min(minX, q[0]);
                maxX = Math.max(maxX, q[0]);
                minY = Math.min(minY, q[1]);
                maxY = Math.max(maxY, q[1]);
                n++;
            }
        }
        o.extentArea = n >= MIN_JOINTS_FOR_EXTENT ? (maxX - minX) * (maxY - minY) : 0.0;
        int bw = box[2] - box[0], bh = box[3] - box[1];
        o.a1 = lineAngle(sh, ank);
        o.h3 = ank != null && nose != null && o.torso != null ? (ank[1] - nose[1]) / o.torso : null;
        o.b1 = bh > 0 ? (double) bw / bh : null;
        o.hip = hip;
        return o;
    }

    /**
     * One frame (call for every frame in time order, also when nobody was found).
     * @param t         frame time in seconds
     * @param boxes     PoseBridge boxes; may be empty
     * @param landmarks the landmarks of each box (null or empty = no landmarks for that box)
     */
    public Frame update(double t, List<int[]> boxes, List<double[][]> landmarks) {
        Person main = null;
        for (int i = 0; i < boxes.size(); i++) {
            double[][] lms = i < landmarks.size() ? landmarks.get(i) : null;
            if (lms == null || lms.length == 0) continue;
            Person p = person(boxes.get(i), lms);
            if (main == null || p.extentArea > main.extentArea) main = p;   // 같으면 앞사람 (Python max 와 같음)
        }
        if (firstTime == null) firstTime = t;
        Double c1 = null;
        if (main != null) {
            int j = before(t);
            Person prev = j >= 0 ? mains.get(j) : null;
            double dt = j >= 0 ? t - times.get(j) : 0;
            if (prev != null && main.hip != null && prev.hip != null && prev.torso != null && dt > 0) {
                c1 = (main.hip[1] - prev.hip[1]) / prev.torso / dt;
            }
        }
        times.add(t);
        mains.add(main);
        // 다음 프레임들이 찾을 시각은 더 늦으므로 그보다 오래된 기록은 버림
        while (times.get(0) < t - DESCENT_SECONDS - DESCENT_TOLERANCE - TIME_TIE) {
            times.remove(0);
            mains.remove(0);
        }
        return main == null ? Frame.NOBODY : new Frame(main.a1, main.h3, main.b1, c1);
    }

    /** Index in the history of the frame closest to t - 0.25 s (as urfall_features.frame_seconds_before), or -1. */
    private int before(double t) {
        if (t - firstTime < DESCENT_SECONDS - TIME_TIE) return -1;   // 아직 그만큼의 기록이 없음
        double target = t - DESCENT_SECONDS, bestD = DESCENT_TOLERANCE;
        int best = -1;
        for (int j = times.size() - 1; j >= 0; j--) {                 // 최근 프레임부터
            if (times.get(j) < target - DESCENT_TOLERANCE - TIME_TIE) break;
            double d = Math.abs(times.get(j) - target);
            if (d <= bestD + TIME_TIE) {                              // 더 가깝거나 같으면 더 이른 프레임
                best = j;
                bestD = Math.min(d, bestD);
            }
        }
        return best;
    }
}
