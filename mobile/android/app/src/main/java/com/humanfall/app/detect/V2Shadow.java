package com.humanfall.app.detect;

import java.util.List;

/**
 * Fall rule v2 running next to the current rule on the same frames, for the log only (docs/fall_rule_v2.md).
 * It never sends anything: alerts stay with LegacyFallLogic. An error here only turns the shadow off, so it
 * cannot stop the current detection.
 *
 * Like FallRuleV2 it alarms only the first time (when to alarm again is not decided yet).
 */
final class V2Shadow {
    /** One frame: the rule's inputs (null = not available) and whether v2 fired on it. */
    static final class Result {
        Double a1, h3, b1, c1;
        boolean fired;
    }

    private final V2Features features;
    private final FallRuleV2 rule = new FallRuleV2();
    private boolean broken;

    /** @param fps the frame rate assumed for the descent speed (see V2Features) */
    V2Shadow(double fps) {
        features = new V2Features(fps);
    }

    /** null when the shadow is off because of an earlier error. */
    Result update(double now, List<int[]> boxes, List<double[][]> landmarks) {
        if (broken) return null;
        try {
            V2Features.Frame f = features.update(boxes, landmarks);
            Result r = new Result();
            r.a1 = f.a1;
            r.h3 = f.h3;
            r.b1 = f.b1;
            r.c1 = f.c1;
            r.fired = rule.update(now, f.a1, f.h3, f.b1, f.c1) != null;
            return r;
        } catch (RuntimeException e) {
            broken = true;
            throw e;
        }
    }

    /** v2's alarm time (seconds, same clock as update), or null. */
    Double alarm() {
        return rule.alarm();
    }

    boolean broken() {
        return broken;
    }
}
