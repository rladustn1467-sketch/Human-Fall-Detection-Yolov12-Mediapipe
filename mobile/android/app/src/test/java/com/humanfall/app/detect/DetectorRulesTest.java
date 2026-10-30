package com.humanfall.app.detect;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class DetectorRulesTest {
    @Test
    public void detectionStoppedByLogoutNeedsTheLoggedInApp() {
        assertFalse(DetectorActivity.canTurnOnHere(true, false));   // 로그아웃으로 멈춤 + 로그인 없이 연 화면
        assertTrue(DetectorActivity.canTurnOnHere(true, true));     // 로그인한 앱에서 연 화면
        assertTrue(DetectorActivity.canTurnOnHere(false, false));   // 직접 끈 것 (로그아웃 아님): 이 휴대폰에서 켬
    }
}
