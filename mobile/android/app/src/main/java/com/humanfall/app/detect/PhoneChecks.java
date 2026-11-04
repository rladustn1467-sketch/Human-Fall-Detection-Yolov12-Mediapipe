package com.humanfall.app.detect;

/**
 * Phone settings that can silently stop detection or its warnings. Shown on the detector screen only while
 * detection is on and something needs fixing. What each maker's battery saver really does needs real phones.
 */
final class PhoneChecks {
    private PhoneChecks() {
    }

    static boolean showBattery(boolean detecting, boolean batteryExempt) {
        return detecting && !batteryExempt;
    }

    static boolean showNotifications(boolean detecting, boolean notificationsOn) {
        return detecting && !notificationsOn;
    }

    static String message(boolean detecting, boolean batteryExempt, boolean notificationsOn) {
        StringBuilder s = new StringBuilder();
        if (showBattery(detecting, batteryExempt)) {
            s.append("휴대폰의 절전 기능 때문에 감지가 멈출 수 있어요. 이 앱의 배터리 제한을 풀어 주세요. "
                    + "휴대폰에 따라 설정의 배터리 메뉴에서 '제한 없음'도 골라야 할 수 있어요.");
        }
        if (showNotifications(detecting, notificationsOn)) {
            if (s.length() > 0) s.append("\n\n");
            s.append("알림이 꺼져 있으면 감지가 멈춰도 이 휴대폰에서 알 수 없어요. 알림을 허용해 주세요.");
        }
        return s.toString();
    }
}
