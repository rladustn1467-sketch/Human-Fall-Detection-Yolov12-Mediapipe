package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

/** FallAlertsV2 on made-up frame series (30 fps), the same cases as tests/test_fall_logic_v2.py AlertsAgainTest. */
public class FallAlertsV2Test {
    private static final double FPS = 30;
    private static final Double[] UP = {85.0, 2.5, 0.4, 0.0};      // 서 있음
    private static final Double[] DOWN = {10.0, 0.0, 2.5, 0.0};    // 바닥에 누움
    private static final Double[] NOBODY = {null, null, null, null};

    private static List<Double[]> series(Object... parts) {
        List<Double[]> out = new ArrayList<>();
        for (int i = 0; i < parts.length; i += 2) {
            for (int k = 0; k < (Integer) parts[i + 1]; k++) out.add((Double[]) parts[i]);
        }
        return out;
    }

    private static List<Double> alarms(List<Double[]> frames) {
        FallAlertsV2 a = new FallAlertsV2();
        for (int i = 0; i < frames.size(); i++) {
            Double[] f = frames.get(i);
            a.update(i / FPS, f[0], f[1], f[2], f[3]);
        }
        return a.alarms();
    }

    @Test
    public void stayingDownAlarmsOnce() {
        assertEquals(1, alarms(series(UP, 30, DOWN, 600)).size());
    }

    @Test
    public void alarmsAgainAfterGettingUpForTwoSeconds() {
        List<Double> got = alarms(series(UP, 30, DOWN, 60, UP, 70, DOWN, 60));
        assertEquals(2, got.size());
        assertTrue(got.get(1) > (30 + 60 + 70) / FPS);
    }

    @Test
    public void shortRiseDoesNotReset() {
        assertEquals(1, alarms(series(UP, 30, DOWN, 60, UP, 50, DOWN, 60)).size());
    }

    @Test
    public void noPersonNeitherResetsNorBreaks() {
        assertEquals(2, alarms(series(UP, 30, DOWN, 60, UP, 30, NOBODY, 20, UP, 31, DOWN, 60)).size());
        assertEquals(1, alarms(series(UP, 30, DOWN, 60, NOBODY, 600, DOWN, 60)).size());
    }

    @Test
    public void firstAlarmSameAsTheRule() {
        List<Double[]> frames = series(UP, 30, DOWN, 60);
        FallRuleV2 rule = new FallRuleV2();
        for (int i = 0; i < frames.size(); i++) {
            Double[] f = frames.get(i);
            rule.update(i / FPS, f[0], f[1], f[2], f[3]);
        }
        assertEquals(rule.alarm(), alarms(frames).get(0));
    }
}
