package com.humanfall.app.detect;

import java.util.ArrayList;
import java.util.List;

/**
 * Connects the phone's pose results to the PC fall logic.
 *
 * Difference from the PC (measured, see the 2c report): the PC finds each person with YOLO first and runs MediaPipe
 * Pose on that box, so its landmarks are fractions of the YOLO box. The phone has no YOLO; MediaPipe Pose Landmarker
 * finds up to two people on the whole frame and gives landmarks as fractions of the frame. Here a person box is made
 * from that person's landmarks (their extent plus a margin, like a person detector's box around the whole body) and
 * the landmarks are re-expressed as fractions of that box, so the same rule (angle, aspect ratio) can be applied.
 */
public final class PoseBridge {
    /** 관절 범위 바깥 여유 (몸 전체를 감싸는 사람 상자에 가깝게: 머리카락·손발 끝) */
    static final double BOX_MARGIN = 0.10;

    public static final class People {
        public final List<int[]> boxes = new ArrayList<>();
        public final List<double[][]> landmarks = new ArrayList<>();
        /** index of each person in the input (= its segmentation mask) */
        public final List<Integer> sources = new ArrayList<>();
    }

    /**
     * @param poses  one entry per person: [33][x, y, z, visibility] normalized to the frame (MediaPipe output)
     * @param width  frame width in pixels
     * @param height frame height in pixels
     */
    public static People fromFrame(List<double[][]> poses, int width, int height) {
        People out = new People();
        for (int n = 0; n < poses.size(); n++) {
            double[][] p = poses.get(n);
            if (p == null || p.length == 0) continue;
            double minX = Double.MAX_VALUE, minY = Double.MAX_VALUE, maxX = -Double.MAX_VALUE, maxY = -Double.MAX_VALUE;
            for (double[] q : p) {
                minX = Math.min(minX, q[0] * width);
                maxX = Math.max(maxX, q[0] * width);
                minY = Math.min(minY, q[1] * height);
                maxY = Math.max(maxY, q[1] * height);
            }
            double mx = (maxX - minX) * BOX_MARGIN, my = (maxY - minY) * BOX_MARGIN;
            int x1 = (int) Math.max(0, Math.floor(minX - mx));
            int y1 = (int) Math.max(0, Math.floor(minY - my));
            int x2 = (int) Math.min(width, Math.ceil(maxX + mx));
            int y2 = (int) Math.min(height, Math.ceil(maxY + my));
            if (x2 - x1 < 2 || y2 - y1 < 2) continue;   // 화면 밖으로 거의 다 나간 사람
            double[][] crop = new double[p.length][4];
            for (int i = 0; i < p.length; i++) {
                crop[i][0] = (p[i][0] * width - x1) / (x2 - x1);
                crop[i][1] = (p[i][1] * height - y1) / (y2 - y1);
                crop[i][2] = p[i][2];
                crop[i][3] = p[i][3];
            }
            out.boxes.add(new int[]{x1, y1, x2, y2});
            out.landmarks.add(crop);
            out.sources.add(n);
        }
        return out;
    }
}
