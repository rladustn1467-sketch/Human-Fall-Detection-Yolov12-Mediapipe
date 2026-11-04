package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** What the detector screen asks the person to fix on this phone. */
public class PhoneChecksTest {
    @Test
    public void nothingIsShownWhenThePhoneIsReady() {
        assertEquals("", PhoneChecks.message(true, true, true));
    }

    @Test
    public void onlyWhatIsWrongIsShown() {
        assertTrue(PhoneChecks.message(true, false, true).contains("배터리"));
        assertFalse(PhoneChecks.message(true, false, true).contains("알림"));
        assertTrue(PhoneChecks.message(true, true, false).contains("알림"));
        assertFalse(PhoneChecks.message(true, true, false).contains("배터리"));
        assertTrue(PhoneChecks.message(true, false, false).contains("배터리"));
        assertTrue(PhoneChecks.message(true, false, false).contains("알림"));
    }

    @Test
    public void aPhoneThatIsNotDetectingIsNotBothered() {
        assertEquals("", PhoneChecks.message(false, false, false));
    }

    @Test
    public void aDetectionOnlyPhoneNeedsItsCharger() {
        assertTrue(PhoneChecks.power(true, false, 80, false, false).contains("충전기"));
        assertEquals("", PhoneChecks.power(true, false, 80, true, false));
    }

    @Test
    public void aPhoneInEverydayUseIsOnlyWarnedWhenLow() {
        assertEquals("", PhoneChecks.power(true, true, 80, false, false));
        assertTrue(PhoneChecks.power(true, true, 20, false, false).contains("배터리"));
        assertEquals("", PhoneChecks.power(true, true, 20, true, false));
        assertEquals("", PhoneChecks.power(true, true, -1, false, false));     // 잔량을 모름
    }

    @Test
    public void aHotPhoneIsAlwaysMentioned() {
        assertTrue(PhoneChecks.power(true, true, 80, true, true).contains("뜨거워요"));
        assertTrue(PhoneChecks.power(true, false, 80, false, true).contains("충전기"));
        assertEquals("", PhoneChecks.power(false, false, 5, false, true));     // 감지 중이 아니면 묻지 않음
    }

    @Test
    public void buttonsFollowTheSameRule() {
        assertTrue(PhoneChecks.showBattery(true, false));
        assertFalse(PhoneChecks.showBattery(true, true));
        assertFalse(PhoneChecks.showBattery(false, false));
        assertTrue(PhoneChecks.showNotifications(true, false));
        assertFalse(PhoneChecks.showNotifications(true, true));
        assertFalse(PhoneChecks.showNotifications(false, false));
    }
}
