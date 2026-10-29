package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.List;

/**
 * FallRuleV2 for a camera that keeps running, a Java copy of fall_logic.v2.FallAlertsV2 (user decisions 2026-10-29,
 * docs/fall_rule_v2.md): after an alarm nothing more is reported while the person stays down (the server's incident
 * follows up); once frames that are not wide have lasted UP_SECONDS (gaps without values up to gapSeconds allowed,
 * a wide frame breaks it) the rule starts over and can alarm again. Only the main person is judged.
 */
public final class FallAlertsV2 {
    /** 알림 뒤 이만큼 '넓게 본 낮은 자세'가 아니면 일어난 것으로 보고 처음부터 */
    public static final double UP_SECONDS = 2.0;

    private final FallRuleV2.Params p;
    private final double upSeconds;
    private FallRuleV2 rule;
    private final List<Double> alarms = new ArrayList<>();
    private Double upStart, upLast;

    public FallAlertsV2() {
        this(FallRuleV2.Params.DEFAULT, UP_SECONDS);
    }

    public FallAlertsV2(FallRuleV2.Params params, double upSeconds) {
        this.p = params;
        this.upSeconds = upSeconds;
        this.rule = new FallRuleV2(params);
    }

    /** Every alarm time so far (seconds). */
    public List<Double> alarms() {
        return alarms;
    }

    /** One frame in time order. Returns the alarm time when it alarms on this frame, else null. */
    public Double update(double t, Double a1, Double h3, Double b1, Double c1) {
        if (rule.alarm() == null) {
            Double fired = rule.update(t, a1, h3, b1, c1);
            if (fired != null) {
                alarms.add(fired);
                upStart = null;
            }
            return fired;
        }
        // 알린 뒤: 다시 알리지 않고 일어났는지만 봄
        boolean hasValue = a1 != null || h3 != null || b1 != null;
        if (hasValue && !rule.isWide(a1, h3, b1)) {
            if (upStart == null || t - upLast > p.gapSeconds) upStart = t;
            upLast = t;
            if (upLast - upStart >= upSeconds) {
                rule = new FallRuleV2(p);
                upStart = null;
            }
        } else if (hasValue) {
            upStart = null;
        }
        return null;
    }
}
