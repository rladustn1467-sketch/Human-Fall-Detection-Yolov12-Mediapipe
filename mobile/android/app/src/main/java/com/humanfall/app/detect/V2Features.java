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
 * C1 compares the main person's hip with the main person of {@code round(0.25 * fps)} frames before, so it
 * assumes frames at a steady rate (as in the recorded test videos). On the phone the camera rate varies
 * (KEEP_ONLY_LATEST) - not checked on a real phone yet (docs/fall_rule_v2.md).
 */
public final class V2Features {
    static final double VIS_MIN = 0.5;
    static final int NOSE = 0, L_SH = 11, R_SH = 12, L_HIP = 23, R_HIP = 24, L_ANK = 27, R_ANK = 28;
    static final int MIN_JOINTS_FOR_EXTENT = 5;
    static final double DESCENT_SECONDS = 0.25;

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

    private final double fps;
    private final int back;
    private final List<Person> mains = new ArrayList<>();   // 최근 프레임마다 주 인물 (없으면 null)

    /** @param fps the frame rate of the input (UR Fall 30, CAUCAFall 20) */
    public V2Features(double fps) {
        this.fps = fps;
        this.back = (int) Math.rint(DESCENT_SECONDS * fps);   // Python round() 처럼 짝수 쪽으로 반올림
    }

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
     * One frame (call for every frame, also when nobody was found).
     * @param boxes     PoseBridge boxes; may be empty
     * @param landmarks the landmarks of each box (null or empty = no landmarks for that box)
     */
    public Frame update(List<int[]> boxes, List<double[][]> landmarks) {
        Person main = null;
        for (int i = 0; i < boxes.size(); i++) {
            double[][] lms = i < landmarks.size() ? landmarks.get(i) : null;
            if (lms == null || lms.length == 0) continue;
            Person p = person(boxes.get(i), lms);
            if (main == null || p.extentArea > main.extentArea) main = p;   // 같으면 앞사람 (Python max 와 같음)
        }
        mains.add(main);
        int k = mains.size() - 1;
        if (main == null) {
            trim();
            return Frame.NOBODY;
        }
        Double c1 = null;
        Person prev = k - back >= 0 ? mains.get(k - back) : null;
        if (prev != null && main.hip != null && prev.hip != null && prev.torso != null && back > 0) {
            c1 = (main.hip[1] - prev.hip[1]) / prev.torso / (back / fps);
        }
        trim();
        return new Frame(main.a1, main.h3, main.b1, c1);
    }

    /** Keep only the history the speed needs. */
    private void trim() {
        while (mains.size() > back + 1) mains.remove(0);
    }
}
