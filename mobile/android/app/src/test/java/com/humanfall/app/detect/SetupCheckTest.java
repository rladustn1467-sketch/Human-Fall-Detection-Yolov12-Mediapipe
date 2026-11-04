package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.humanfall.app.detect.SetupCheck.Result;
import org.junit.Test;

/** The detector screen's check of where the phone stands, and which way up it is. */
public class SetupCheckTest {
    private static double[][] body(double noseY, double ankleY, double visibility) {
        double[][] p = new double[33][4];
        for (double[] v : p) {
            v[0] = 0.5;
            v[1] = 0.5;
        }
        p[0][1] = noseY;
        p[0][3] = 1;
        p[27][1] = ankleY;
        p[27][3] = visibility;
        return p;
    }

    @Test
    public void wholeBodyNeedsHeadAndAFootInsideTheFrame() {
        assertTrue(SetupCheck.wholeBody(body(0.1, 0.9, 0.9)));
        assertFalse(SetupCheck.wholeBody(body(0.1, 0.9, 0.2)));    // 발목을 잘 못 봄
        assertFalse(SetupCheck.wholeBody(body(0.1, 1.2, 0.9)));    // 화면 아래로 잘림 (MediaPipe 가 추측한 위치)
        assertFalse(SetupCheck.wholeBody(body(-0.1, 0.9, 0.9)));   // 머리가 잘림
        assertFalse(SetupCheck.wholeBody(new double[3][4]));
    }

    @Test
    public void resultOrder() {
        assertEquals(Result.DARK, SetupCheck.of(0, 10, false));
        assertEquals(Result.DARK, SetupCheck.of(1, 10, true));
        assertEquals(Result.NOBODY, SetupCheck.of(0, 120, false));
        assertEquals(Result.PARTIAL, SetupCheck.of(1, 120, false));
        assertEquals(Result.GOOD, SetupCheck.of(1, 120, true));
    }

    @Test
    public void everyResultHasWordsForThePerson() {
        for (Result r : Result.values()) assertFalse(SetupCheck.text(r).isEmpty());
    }

    @Test
    public void meanBrightness() {
        int[] black = new int[64], white = new int[64];
        java.util.Arrays.fill(black, 0xFF000000);
        java.util.Arrays.fill(white, 0xFFFFFFFF);
        assertEquals(0, SetupCheck.meanBrightness(black), 0.01);
        assertEquals(255, SetupCheck.meanBrightness(white), 0.01);
    }

    @Test
    public void rotationFollowsThePhone() {
        assertEquals(0, SetupCheck.rotation(0, 0));
        assertEquals(3, SetupCheck.rotation(90, 0));     // Surface.ROTATION_270
        assertEquals(2, SetupCheck.rotation(180, 0));    // Surface.ROTATION_180
        assertEquals(1, SetupCheck.rotation(270, 0));    // Surface.ROTATION_90
        assertEquals(0, SetupCheck.rotation(350, 0));
    }

    @Test
    public void flatOrShakyPhoneKeepsTheLastRotation() {
        assertEquals(1, SetupCheck.rotation(-1, 1));     // 바닥에 눕힘: 방향을 알 수 없음
        assertEquals(0, SetupCheck.rotation(50, 0));     // 경계 근처는 그대로
        assertEquals(3, SetupCheck.rotation(40, 3));
        assertEquals(3, SetupCheck.rotation(60, 0));
    }
}
