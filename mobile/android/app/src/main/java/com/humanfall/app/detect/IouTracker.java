package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * IoU person tracker: a Java copy of fall_logic/tracker.py (the PC detector's FallDetector.track_persons).
 * Known issues kept on purpose: matching is not one-to-one, a tracker created earlier in the same frame is a
 * candidate for later boxes, expiry is checked only when trackers existed at the start of the call.
 */
final class IouTracker {
    static final double MIN_IOU = 0.3;            // 같은 사람으로 볼 최소 IoU (원본 값)
    static final double EXPIRE_SECONDS = 5.0;      // 이 시간(초) 넘게 안 보이면 추적 정보 삭제 (원본 값)

    private static final class Track {
        int[] box;
        double lastSeen;

        Track(int[] box, double lastSeen) {
            this.box = box;
            this.lastSeen = lastSeen;
        }
    }

    /** box index → person ID (in box order), and the IDs removed this call. */
    static final class Result {
        final LinkedHashMap<Integer, Integer> boxToId = new LinkedHashMap<>();
        final List<Integer> expired = new ArrayList<>();
    }

    private int nextPersonId = 1;
    private final LinkedHashMap<Integer, Track> trackers = new LinkedHashMap<>();   // 원본 dict 와 같은 순서

    Result update(List<int[]> boxes, double now) {
        Result r = new Result();
        if (trackers.isEmpty()) {
            for (int i = 0; i < boxes.size(); i++) {
                trackers.put(nextPersonId, new Track(boxes.get(i), now));
                r.boxToId.put(i, nextPersonId);
                nextPersonId++;
            }
            return r;
        }
        for (int i = 0; i < boxes.size(); i++) {
            int[] cur = boxes.get(i);
            double bestIou = MIN_IOU;
            Integer bestId = null;
            for (Map.Entry<Integer, Track> e : trackers.entrySet()) {
                int[] prev = e.getValue().box;
                int x1 = Math.max(cur[0], prev[0]);
                int y1 = Math.max(cur[1], prev[1]);
                int x2 = Math.min(cur[2], prev[2]);
                int y2 = Math.min(cur[3], prev[3]);
                if (x2 < x1 || y2 < y1) continue;
                long curArea = (long) (cur[2] - cur[0]) * (cur[3] - cur[1]);
                long prevArea = (long) (prev[2] - prev[0]) * (prev[3] - prev[1]);
                long inter = (long) (x2 - x1) * (y2 - y1);
                long union = curArea + prevArea - inter;
                // 넓이 0: 원본(numpy)은 nan/inf 가 되어 매칭되지 않음 → double 나눗셈도 같은 nan/inf
                double iou = (double) inter / (double) union;
                if (iou > bestIou) {
                    bestIou = iou;
                    bestId = e.getKey();
                }
            }
            if (bestId != null) {
                r.boxToId.put(i, bestId);
                Track t = trackers.get(bestId);
                t.box = cur;
                t.lastSeen = now;
            } else {
                trackers.put(nextPersonId, new Track(cur, now));
                r.boxToId.put(i, nextPersonId);
                nextPersonId++;
            }
        }
        for (Iterator<Map.Entry<Integer, Track>> it = trackers.entrySet().iterator(); it.hasNext(); ) {
            Map.Entry<Integer, Track> e = it.next();
            if (now - e.getValue().lastSeen > EXPIRE_SECONDS) {
                r.expired.add(e.getKey());
                it.remove();
            }
        }
        return r;
    }
}
