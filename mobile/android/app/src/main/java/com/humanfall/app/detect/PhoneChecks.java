package com.humanfall.app.detect;

/**
 * Phone settings that can silently stop detection or its warnings. Shown on the detector screen only while
 * detection is on and something needs fixing. What each maker's battery saver really does needs real phones.
 */
final class PhoneChecks {
    private static final int LOW_BATTERY_PERCENT = 20;

    private PhoneChecks() {
    }

    static boolean showBattery(boolean detecting, boolean batteryExempt) {
        return detecting && !batteryExempt;
    }

    static boolean showNotifications(boolean detecting, boolean notificationsOn) {
        return detecting && !notificationsOn;
    }

    /** Charger and heat. ownPhone: a phone in everyday use is only warned when low; battery -1 = unknown. */
    static String power(boolean detecting, boolean ownPhone, int battery, boolean charging, boolean hot) {
        if (!detecting) return "";
        StringBuilder s = new StringBuilder();
        if (hot) s.append("휴대폰이 뜨거워요. 감지가 느려지거나 멈출 수 있어요. 그늘진 곳에 두고 케이스를 벗겨 주세요.");
        String charge = charging ? ""
                : !ownPhone ? "충전기가 빠져 있어요. 감지 전용 휴대폰은 충전기를 꽂아 두세요."
                : battery >= 0 && battery <= LOW_BATTERY_PERCENT ? "배터리가 얼마 남지 않았어요. 충전해 주세요." : "";
        if (!charge.isEmpty() && s.length() > 0) s.append("\n\n");
        return s.append(charge).toString();
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
