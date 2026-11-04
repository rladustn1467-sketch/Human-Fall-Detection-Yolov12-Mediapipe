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
    public void buttonsFollowTheSameRule() {
        assertTrue(PhoneChecks.showBattery(true, false));
        assertFalse(PhoneChecks.showBattery(true, true));
        assertFalse(PhoneChecks.showBattery(false, false));
        assertTrue(PhoneChecks.showNotifications(true, false));
        assertFalse(PhoneChecks.showNotifications(true, true));
        assertFalse(PhoneChecks.showNotifications(false, false));
    }
}
