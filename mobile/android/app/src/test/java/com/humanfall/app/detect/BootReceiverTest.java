package com.humanfall.app.detect;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** After a restart, only a phone that was detecting gets the '감지가 멈춰 있어요' reminder. */
public class BootReceiverTest {
    @Test
    public void detectingPhoneIsReminded() {
        assertTrue(BootReceiver.shouldRemind(true, false, false, true));
    }

    @Test
    public void otherPhonesAreNot() {
        assertFalse(BootReceiver.shouldRemind(false, false, false, true));   // 감지 기기로 연결 안 됨
        assertFalse(BootReceiver.shouldRemind(true, true, false, true));     // 앱에서 기기 삭제됨
        assertFalse(BootReceiver.shouldRemind(true, false, true, true));     // 로그아웃으로 멈춤
        assertFalse(BootReceiver.shouldRemind(true, false, false, false));   // 이 휴대폰에서 감지를 꺼 둠
    }
}
