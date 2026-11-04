package com.humanfall.app.detect;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

public class DetectorRulesTest {
    @Test
    public void detectionStoppedByLogoutNeedsTheLoggedInApp() {
        assertFalse(DetectorActivity.canTurnOnHere(true, false));   // 로그아웃으로 멈춤 + 로그인 없이 연 화면
        assertTrue(DetectorActivity.canTurnOnHere(true, true));     // 로그인한 앱에서 연 화면
        assertTrue(DetectorActivity.canTurnOnHere(false, false));   // 직접 끈 것 (로그아웃 아님): 이 휴대폰에서 켬
    }

    @Test
    public void analysisFailsWhenFramesComeButNoneIsAnalysedForFiveSeconds() {
        assertFalse(DetectorRuntime.analysisFailing(0, 0));                 // 아직 프레임 없음
        assertFalse(DetectorRuntime.analysisFailing(1000, 1000));           // 첫 프레임
        assertFalse(DetectorRuntime.analysisFailing(5999, 1000));
        assertTrue(DetectorRuntime.analysisFailing(6000, 1000));
        assertFalse(DetectorRuntime.analysisFailing(6000, 6100));           // 분석이 다시 됨
    }

    @Test
    public void cameraStallsWhenFramesStopAfterTheyHadStarted() {
        assertFalse(DetectorRuntime.cameraStalled(0, 60_000));              // 아직 준비 중
        assertFalse(DetectorRuntime.cameraStalled(1000, 5999));
        assertTrue(DetectorRuntime.cameraStalled(1000, 6000));
    }

    @Test
    public void aPhotoErrorDoesNotLoseTheFall() {
        byte[] jpeg = {1, 2};
        List<Throwable> errors = new ArrayList<>();
        assertArrayEquals(jpeg, FallPipeline.photoOrNull(() -> jpeg, errors::add));
        assertEquals(0, errors.size());
        assertNull(FallPipeline.photoOrNull(() -> { throw new IllegalStateException("시험용"); }, errors::add));
        assertNull(FallPipeline.photoOrNull(() -> { throw new OutOfMemoryError("시험용"); }, errors::add));
        assertEquals(2, errors.size());
    }
}
