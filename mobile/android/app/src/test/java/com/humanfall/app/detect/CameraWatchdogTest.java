package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.humanfall.app.detect.CameraWatchdog.Action;
import org.junit.Test;

/** What the detection service does when frames or analysis stop. */
public class CameraWatchdogTest {
    private static final long S = 1000;

    private static CameraWatchdog started(long at) {
        CameraWatchdog w = new CameraWatchdog();
        w.cameraStarted(at);
        return w;
    }

    @Test
    public void healthyCameraIsLeftAlone() {
        CameraWatchdog w = started(0);
        assertEquals(Action.NONE, w.check(60 * S, 60 * S - 100, 60 * S - 100));
        assertFalse(w.recovering());
    }

    @Test
    public void slowStartIsGivenTime() {
        CameraWatchdog w = started(0);
        assertEquals(Action.NONE, w.check(14 * S, 0, 0));
        assertEquals(Action.RESTART_CAMERA, w.check(15 * S, 0, 0));    // 첫 프레임이 끝내 안 옴
    }

    @Test
    public void stoppedFramesRestartTheCamera() {
        CameraWatchdog w = started(0);
        w.check(10 * S, 10 * S, 10 * S);
        assertEquals(Action.NONE, w.check(24 * S, 10 * S, 10 * S));
        assertEquals(Action.RESTART_CAMERA, w.check(25 * S, 10 * S, 10 * S));
        assertTrue(w.recovering());
    }

    @Test
    public void framesWithoutAnalysisRestartTheAnalysis() {
        CameraWatchdog w = started(0);
        assertEquals(Action.RESTART_ANALYSIS, w.check(30 * S, 30 * S, 10 * S));
    }

    @Test
    public void retriesWaitLongerThenAskTheUserOnce() {
        CameraWatchdog w = started(0);
        assertEquals(Action.RESTART_CAMERA, w.check(15 * S, 0, 0));    // 1번째
        w.cameraStarted(15 * S);
        assertEquals(Action.NONE, w.check(44 * S, 0, 0));
        assertEquals(Action.RESTART_CAMERA, w.check(45 * S, 0, 0));    // 30초 뒤 2번째
        w.cameraStarted(45 * S);
        assertEquals(Action.NONE, w.check(104 * S, 0, 0));
        assertEquals(Action.RESTART_CAMERA, w.check(105 * S, 0, 0));   // 60초 뒤 3번째
        w.cameraStarted(105 * S);
        assertEquals(Action.ASK_USER, w.check(106 * S, 0, 0));         // 3번 실패: 사람에게 알림 (한 번만)
        assertEquals(Action.NONE, w.check(107 * S, 0, 0));
        assertEquals(Action.RESTART_CAMERA, w.check(405 * S, 0, 0));   // 그 뒤로는 5분마다 계속 시도
    }

    @Test
    public void framesComingBackEndTheRecovery() {
        CameraWatchdog w = started(0);
        w.check(15 * S, 0, 0);
        w.cameraStarted(15 * S);
        assertTrue(w.recovering());
        assertEquals(Action.RECOVERED, w.check(20 * S, 20 * S, 20 * S));
        assertFalse(w.recovering());
        assertEquals(Action.NONE, w.check(21 * S, 21 * S, 21 * S));
    }

    @Test
    public void userOpeningTheAppTriesAgainAtOnce() {
        CameraWatchdog w = started(0);
        assertFalse(w.userAsked());                                    // 정상이면 아무것도 안 함
        w.check(15 * S, 0, 0);
        assertTrue(w.userAsked());                                     // 복구 중이면 바로 다시 시도
        assertFalse(w.recovering());
    }
}
