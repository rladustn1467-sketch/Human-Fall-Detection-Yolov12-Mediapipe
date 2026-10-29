package com.humanfall.app.detect;

import java.util.List;

/**
 * Fall rule v2 running next to the current rule on the same frames, for the log only (docs/fall_rule_v2.md).
 * It never sends anything: alerts stay with LegacyFallLogic. An error here only turns the shadow off, so it
 * cannot stop the current detection.
 *
 * It alarms like FallAlertsV2: once while the person stays down, again after they got up.
 */
final class V2Shadow {
    /** One frame: the rule's inputs (null = not available) and whether v2 fired on it. */
    static final class Result {
        Double a1, h3, b1, c1;
        boolean fired;
    }

    private final V2Features features;
    private final FallAlertsV2 alerts = new FallAlertsV2();
    private boolean broken;

    V2Shadow() {
        features = new V2Features();
    }

    /** null when the shadow is off because of an earlier error. */
    Result update(double now, List<int[]> boxes, List<double[][]> landmarks) {
        if (broken) return null;
        try {
            V2Features.Frame f = features.update(now, boxes, landmarks);
            Result r = new Result();
            r.a1 = f.a1;
            r.h3 = f.h3;
            r.b1 = f.b1;
            r.c1 = f.c1;
            r.fired = alerts.update(now, f.a1, f.h3, f.b1, f.c1) != null;
            return r;
        } catch (RuntimeException e) {
            broken = true;
            throw e;
        }
    }

    /** v2's alarm times so far (seconds, same clock as update). */
    List<Double> alarms() {
        return alerts.alarms();
    }

    boolean broken() {
        return broken;
    }
}
