package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Fall rule v2, a Java copy of fall_logic/v2.py (docs/fall_rule_v2.md), checked against the Python output by
 * FallRuleV2GoldenTest. FallPipeline runs it for the log only (V2Shadow); alerts still come from LegacyFallLogic.
 *
 * low  = A1 < lowAngle or H3 < lowHead;  wide = low or B1 > wideBox
 * (A) fast drop:  speed smoothed over 3 consecutive values (median) >= dropSpeed, then within dropWindow
 *                 seconds at least dropFrames frames that are wide (or low)
 * (B) stays down: wide frames for staySeconds in a row; up to gapSeconds without any value do not break it,
 *                 a frame with values that is not wide does
 * fall = (A) or (B). The speed of a frame is judged when the next frame arrives (one frame of delay).
 */
public final class FallRuleV2 {
    public static final class Params {
        public final double lowAngle, lowHead, wideBox, dropSpeed, dropWindow, staySeconds, gapSeconds;
        public final boolean dropAfterWide;
        public final int dropFrames;

        public Params(double lowAngle, double lowHead, double wideBox, double dropSpeed, boolean dropAfterWide,
                      int dropFrames, double dropWindow, double staySeconds, double gapSeconds) {
            this.lowAngle = lowAngle;
            this.lowHead = lowHead;
            this.wideBox = wideBox;
            this.dropSpeed = dropSpeed;
            this.dropAfterWide = dropAfterWide;
            this.dropFrames = dropFrames;
            this.dropWindow = dropWindow;
            this.staySeconds = staySeconds;
            this.gapSeconds = gapSeconds;
        }

        /** The values chosen on the tune videos (2026-10-29, docs/fall_rule_v2.md); same as Python Params(). */
        public static final Params DEFAULT = new Params(40.0, 0.3, 1.5, 2.0, true, 3, 1.0, 1.0, 1.0);
    }

    private final Params p;
    private Double alarm;
    private final List<Double> speeds = new ArrayList<>();   // 최근 3개 속도 (평활용)
    private final List<Double> times = new ArrayList<>();
    private final List<double[]> pending = new ArrayList<>(); // (A): [시작 시각, 확인된 프레임 수]
    private Double runStart, runLast;                         // (B)

    public FallRuleV2() {
        this(Params.DEFAULT);
    }

    public FallRuleV2(Params params) {
        this.p = params;
    }

    /** The first alarm time (seconds), or null. */
    public Double alarm() {
        return alarm;
    }

    private static Double median3(Double a, Double b, Double c) {
        List<Double> v = new ArrayList<>();
        for (Double x : Arrays.asList(a, b, c)) if (x != null) v.add(x);
        if (v.isEmpty()) return null;
        v.sort(null);
        int n = v.size();
        return n % 2 == 1 ? v.get(n / 2) : (v.get(n / 2 - 1) + v.get(n / 2)) / 2;
    }

    /** One frame in time order. Returns the alarm time when the rule fires on this frame (only the first time). */
    public Double update(double t, Double a1, Double h3, Double b1, Double c1) {
        boolean low = (a1 != null && a1 < p.lowAngle) || (h3 != null && h3 < p.lowHead);
        boolean wide = low || (b1 != null && b1 > p.wideBox);
        boolean hasValue = a1 != null || h3 != null || b1 != null;
        Double fired = null;

        // (A) 이번 프레임이 지난 하락 후보들의 확인 프레임이 되는지
        boolean check = p.dropAfterWide ? wide : low;
        List<double[]> still = new ArrayList<>();
        for (double[] c : pending) {
            if (t - c[0] > p.dropWindow) continue;
            if (check) {
                c[1] += 1;
                if (c[1] >= p.dropFrames) {
                    fired = earliest(fired, t);
                    continue;
                }
            }
            still.add(c);
        }
        pending.clear();
        pending.addAll(still);
        // 한 프레임 늦게: 직전 프레임의 평활 속도 (직전·전전·지금 값의 중앙값)
        speeds.add(c1);
        times.add(t);
        if (speeds.size() >= 2) {
            Double prev = speeds.get(speeds.size() - 2);
            if (prev != null && p.dropSpeed != Double.POSITIVE_INFINITY) {
                Double before = speeds.size() >= 3 ? speeds.get(speeds.size() - 3) : null;
                Double s = median3(before, prev, c1);
                if (s != null && s >= p.dropSpeed) {
                    double start = times.get(times.size() - 2);
                    int n = check && t - start <= p.dropWindow ? 1 : 0;   // 지금 프레임은 그 뒤 첫 프레임
                    if (n >= p.dropFrames) fired = earliest(fired, t);
                    else pending.add(new double[]{start, n});
                }
            }
        }
        while (speeds.size() > 3) {
            speeds.remove(0);
            times.remove(0);
        }

        // (B) 넓게 본 낮은 자세 유지
        if (wide) {
            if (runStart == null || t - runLast > p.gapSeconds) runStart = t;
            runLast = t;
            if (p.staySeconds != Double.POSITIVE_INFINITY && runLast - runStart >= p.staySeconds) fired = earliest(fired, t);
        } else if (hasValue) {
            runStart = null;
        }

        if (fired != null && alarm == null) {
            alarm = fired;
            return alarm;
        }
        return null;
    }

    private static Double earliest(Double a, double b) {
        return a == null ? b : Math.min(a, b);
    }
}
