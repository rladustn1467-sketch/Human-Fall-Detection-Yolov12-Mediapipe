package com.humanfall.app.detect;

/**
 * Helps the person place the phone: whether someone is seen, whole, in enough light, and which way up the phone is.
 * The limits are first guesses until they are measured on a real phone in a real room.
 */
final class SetupCheck {
    enum Result { NOBODY, DARK, PARTIAL, GOOD }

    static final double DARK_BELOW = 35;       // 평균 밝기 0~255
    private static final double VISIBLE = 0.5;
    private static final int NOSE = 0, LEFT_ANKLE = 27, RIGHT_ANKLE = 28;
    private static final int ROTATION_MARGIN = 15;

    private SetupCheck() {
    }

    /** landmarks: one person, normalized to the frame. Head and at least one foot are seen inside the frame. */
    static boolean wholeBody(double[][] landmarks) {
        if (landmarks.length <= RIGHT_ANKLE) return false;
        return seen(landmarks[NOSE]) && (seen(landmarks[LEFT_ANKLE]) || seen(landmarks[RIGHT_ANKLE]));
    }

    private static boolean seen(double[] point) {
        return point[3] >= VISIBLE && point[0] >= 0 && point[0] <= 1 && point[1] >= 0 && point[1] <= 1;
    }

    static Result of(int persons, double brightness, boolean wholeBody) {
        if (brightness < DARK_BELOW) return Result.DARK;
        if (persons == 0) return Result.NOBODY;
        return wholeBody ? Result.GOOD : Result.PARTIAL;
    }

    static String text(Result r) {
        switch (r) {
            case GOOD:
                return "사람이 잘 보여요. 이 자리에 두면 돼요.";
            case PARTIAL:
                return "몸 전체가 보이지 않아요. 머리부터 발까지 보이도록 휴대폰을 더 멀리 놓아 주세요.";
            case DARK:
                return "너무 어두워요. 불을 켜거나 더 밝은 곳을 보도록 놓아 주세요.";
            default:
                return "사람이 보이지 않아요. 카메라 앞에 서서 전신이 보이는지 확인해 주세요.";
        }
    }

    static double meanBrightness(int[] argb) {
        long sum = 0;
        int count = 0;
        for (int i = 0; i < argb.length; i += 16) {   // 설치 확인에는 일부 픽셀로 충분
            int p = argb[i];
            sum += (((p >> 16) & 0xFF) * 299 + ((p >> 8) & 0xFF) * 587 + (p & 0xFF) * 114 + 500) / 1000;
            count++;
        }
        return count == 0 ? 0 : (double) sum / count;
    }

    /**
     * The camera rotation (Surface.ROTATION_*: 0 to 3) for the way the phone is held, from OrientationEventListener
     * degrees. The screen's rotation cannot be used: this runs in the background and the screen may be locked.
     * -1 (lying flat) and angles near a boundary keep the current rotation.
     */
    static int rotation(int degrees, int current) {
        if (degrees < 0) return current;
        int next = ((degrees + 45) % 360) / 90;                 // 0: 정방향, 1: 90도, 2: 180도, 3: 270도
        int rotation = (4 - next) % 4;
        if (rotation == current) return current;
        int centre = next * 90;
        int off = Math.abs(((degrees - centre + 540) % 360) - 180);
        return off <= 45 - ROTATION_MARGIN ? rotation : current;
    }
}
