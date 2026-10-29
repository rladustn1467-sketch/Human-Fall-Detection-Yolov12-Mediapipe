package com.humanfall.app.detect;

import java.util.ArrayDeque;

/**
 * How many frames the phone really analyses per second, and how long one frame takes, over the last WINDOW_MS.
 * The camera drops frames it cannot keep up with (KEEP_ONLY_LATEST), so this is the rate the fall rules see.
 * Fall rule v2's fast-drop part gets weaker below about 15 frames per second (docs/fall_rule_v2.md).
 */
final class FrameRate {
    static final long WINDOW_MS = 10_000;
    static final long REPORT_EVERY_MS = 60_000;

    private final ArrayDeque<long[]> frames = new ArrayDeque<>();   // [끝난 시각 ms, 걸린 시간 ms]
    private boolean started;
    private long lastReport;

    /** A frame finished at endMs after taking tookMs. Returns true when a log line is due (first full window, then every minute). */
    synchronized boolean add(long endMs, long tookMs) {
        frames.addLast(new long[]{endMs, tookMs});
        while (!frames.isEmpty() && frames.peekFirst()[0] <= endMs - WINDOW_MS) frames.removeFirst();
        if (!started) {
            started = true;
            lastReport = endMs - REPORT_EVERY_MS + WINDOW_MS;   // 처음에는 창이 찰 때 한 번
        }
        if (endMs - lastReport >= REPORT_EVERY_MS) {
            lastReport = endMs;
            return true;
        }
        return false;
    }

    /** Frames per second over the window (NaN until there are two frames). */
    synchronized double fps() {
        if (frames.size() < 2) return Double.NaN;
        long span = frames.peekLast()[0] - frames.peekFirst()[0];
        return span <= 0 ? Double.NaN : (frames.size() - 1) * 1000.0 / span;
    }

    /** Average analysis time of one frame over the window, in ms (NaN when empty). */
    synchronized double averageMs() {
        if (frames.isEmpty()) return Double.NaN;
        long sum = 0;
        for (long[] f : frames) sum += f[1];
        return sum / (double) frames.size();
    }

    synchronized void clear() {
        frames.clear();
        started = false;
    }
}
