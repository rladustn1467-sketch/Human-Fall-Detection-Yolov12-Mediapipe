package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.Test;

/** A new fall of a person who got up: same cases as tests/test_legacy_engine.py (the golden test covers the rest). */
public class LegacyFallLogicRefallTest {
    private static final int[] BOX = {100, 100, 300, 200};

    private static double[][] pose(boolean lying) {
        double[][] p = new double[33][4];
        for (double[] v : p) v[3] = 1;
        double[][] joints = lying
                ? new double[][]{{0, .1, .5}, {11, .3, .45}, {12, .3, .55}, {23, .6, .45}, {24, .6, .55}, {25, .75, .45}, {26, .75, .55}, {27, .9, .45}, {28, .9, .55}}
                : new double[][]{{0, .5, .1}, {11, .4, .25}, {12, .6, .25}, {23, .45, .55}, {24, .55, .55}, {25, .45, .75}, {26, .55, .75}, {27, .45, .95}, {28, .55, .95}};
        for (double[] j : joints) {
            p[(int) j[0]][0] = j[1];
            p[(int) j[0]][1] = j[2];
        }
        return p;
    }

    private static LegacyFallLogic.Result frame(LegacyFallLogic logic, double now, double[][] lm) {
        List<int[]> boxes = new ArrayList<>();
        boxes.add(BOX);
        List<double[][]> lms = new ArrayList<>();
        lms.add(lm);
        return logic.update(now, boxes, lms);
    }

    @Test
    public void gettingUpForTwoSecondsAllowsANewFall() {
        LegacyFallLogic logic = new LegacyFallLogic();
        assertTrue(frame(logic, 0, pose(true)).fallDetected);
        frame(logic, 1, pose(false));
        frame(logic, 3, pose(false));
        LegacyFallLogic.Result again = frame(logic, 3.1, pose(true));
        assertTrue(again.fallDetected);
        assertEquals(Collections.singletonList(1), again.fallenIds);
    }

    @Test
    public void lessThanTwoSecondsIsNotEnough() {
        LegacyFallLogic logic = new LegacyFallLogic();
        frame(logic, 0, pose(true));
        frame(logic, 1, pose(false));
        frame(logic, 2.9, pose(false));
        assertFalse(frame(logic, 3, pose(true)).fallDetected);
    }

    @Test
    public void framesWithoutAPoseDoNotCountAsGettingUp() {
        LegacyFallLogic logic = new LegacyFallLogic();
        frame(logic, 0, pose(true));
        frame(logic, 1, null);
        frame(logic, 4, null);
        assertFalse(frame(logic, 4.1, pose(true)).fallDetected);
    }
}
