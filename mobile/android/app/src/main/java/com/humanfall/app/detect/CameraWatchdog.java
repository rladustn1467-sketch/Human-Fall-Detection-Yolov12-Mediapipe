package com.humanfall.app.detect;

/**
 * Decides what to do when the camera stops delivering frames (another app took it, Android blocked a background
 * start) or frames stop being analysed. DetectionService calls check() every few seconds while detection is on.
 * It restarts after STALL_MS, waits longer after each failed try, tells the user after MAX_TRIES and keeps trying.
 */
final class CameraWatchdog {
    enum Action { NONE, RESTART_CAMERA, RESTART_ANALYSIS, ASK_USER, RECOVERED }

    static final long STALL_MS = 15_000;
    static final int MAX_TRIES = 3;
    static final long LATE_RETRY_MS = 5 * 60_000;

    private long watchFrom;     // 카메라를 (다시) 켠 시각
    private long lastTryAt;
    private int tries;
    private boolean asked;

    void cameraStarted(long now) {
        watchFrom = now;
    }

    boolean recovering() {
        return tries > 0;
    }

    /** The user opened the app: try again at once if detection is in trouble (true = restart now). */
    boolean userAsked() {
        boolean restart = tries > 0;
        tries = 0;
        asked = false;
        return restart;
    }

    Action check(long now, long lastFrameAt, long lastAnalyzedAt) {
        boolean frames = now - lastFrameAt < STALL_MS;
        boolean analysed = now - lastAnalyzedAt < STALL_MS;
        if (frames && analysed) {
            boolean was = tries > 0;
            tries = 0;
            asked = false;
            return was ? Action.RECOVERED : Action.NONE;
        }
        if (tries >= MAX_TRIES && !asked) {
            asked = true;
            return Action.ASK_USER;
        }
        long since = tries == 0 ? watchFrom : Math.max(watchFrom, lastTryAt);
        if (now - since < waitBeforeTry()) return Action.NONE;
        tries++;
        lastTryAt = now;
        return frames ? Action.RESTART_ANALYSIS : Action.RESTART_CAMERA;
    }

    private long waitBeforeTry() {
        return tries >= MAX_TRIES ? LATE_RETRY_MS : STALL_MS << tries;
    }
}
