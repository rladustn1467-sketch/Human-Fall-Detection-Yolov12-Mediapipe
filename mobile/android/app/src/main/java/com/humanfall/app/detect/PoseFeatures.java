package com.humanfall.app.detect;

import java.util.List;

/**
 * Pose features: a line-by-line Java copy of fall_logic/features.py (which reproduces the PC detector's
 * FallDetector.calculate_pose_features). Landmarks are crop-normalized like on the PC: x is a fraction of the
 * person box width, y of its height. The known issues of the original are kept on purpose (shared history for all
 * people, time step 1 per call, left/right-side width, visibility ignored) so the decisions match the PC.
 * Checked against the Python output by FallLogicGoldenTest.
 */
public final class PoseFeatures {
    /** 코, 어깨, 엉덩이, 무릎, 발목 (MediaPipe Pose 33개 관절 번호) */
    static final int[] KEY_POINTS = {0, 11, 12, 23, 24, 25, 26, 27, 28};
    /** 이전 자세 기록 최대 개수 (모든 사람이 같이 씀) */
    static final int MAX_POSE_HISTORY = 15;

    public double height, angle, velocityY, velocityX, acceleration, jerk;
    public double midShoulderY, midShoulderX, midHipY, midHipX;
    public double aspectRatio, shoulderToHipDistance, hipToFeetDistance, timestamp;

    /**
     * Features for one person, or null; appended to the shared history (trimmed to 15) like the original.
     *
     * @param lm landmarks [index][x, y, z, visibility], crop-normalized; null or empty = no pose
     */
    public static PoseFeatures compute(double[][] lm, List<PoseFeatures> prevPoses, double now) {
        if (lm == null || lm.length == 0) return null;
        int found = 0;
        for (int i : KEY_POINTS) if (i < lm.length) found++;
        if (found < KEY_POINTS.length) return null;

        double headY = lm[0][1];
        double leftAnkleY = lm[27][1];
        double rightAnkleY = lm[28][1];
        double ankleY = (leftAnkleY + rightAnkleY) / 2;
        double height = Math.abs(ankleY - headY);

        double midShoulderX = (lm[11][0] + lm[12][0]) / 2;
        double midShoulderY = (lm[11][1] + lm[12][1]) / 2;
        double midHipX = (lm[23][0] + lm[24][0]) / 2;
        double midHipY = (lm[23][1] + lm[24][1]) / 2;

        double dx = midHipX - midShoulderX;
        double dy = midHipY - midShoulderY;
        double angle = Math.atan2(dx, dy) * 180.0 / Math.PI;   // Python math.degrees 와 같은 계산 순서

        double feetX = (lm[27][0] + lm[28][0]) / 2;
        double feetY = (lm[27][1] + lm[28][1]) / 2;

        double leftMostX = Math.min(Math.min(lm[11][0], lm[23][0]), Math.min(lm[25][0], lm[27][0]));
        double rightMostX = Math.max(Math.max(lm[12][0], lm[24][0]), Math.max(lm[26][0], lm[28][0]));
        double topMostY = Math.min(Math.min(lm[0][1], lm[11][1]), lm[12][1]);
        double bottomMostY = Math.max(lm[27][1], lm[28][1]);

        double bboxWidth = rightMostX - leftMostX;
        double bboxHeight = bottomMostY - topMostY;
        double aspectRatio = bboxHeight / Math.max(bboxWidth, 0.0001);   // 0 으로 나누기 방지 (원본 그대로)

        double shoulderToHip = Math.sqrt(Math.pow(midShoulderX - midHipX, 2) + Math.pow(midShoulderY - midHipY, 2));
        double hipToFeet = Math.sqrt(Math.pow(midHipX - feetX, 2) + Math.pow(midHipY - feetY, 2));

        double velocityY = 0, velocityX = 0, acceleration = 0, jerk = 0;
        if (!prevPoses.isEmpty()) {
            PoseFeatures prev = prevPoses.get(prevPoses.size() - 1);
            double timeDiff = 1;   // 원본과 같이 프레임 간격을 1로 가정
            velocityY = (midShoulderY - prev.midShoulderY) / timeDiff;
            velocityX = (midShoulderX - prev.midShoulderX) / timeDiff;
            if (prevPoses.size() >= 2) {
                PoseFeatures prev2 = prevPoses.get(prevPoses.size() - 2);
                double prevVelocityY = (prev.midShoulderY - prev2.midShoulderY) / timeDiff;
                acceleration = (velocityY - prevVelocityY) / timeDiff;
                if (prevPoses.size() >= 3) {
                    PoseFeatures prev3 = prevPoses.get(prevPoses.size() - 3);
                    double prevAcceleration = (prevVelocityY - (prev2.midShoulderY - prev3.midShoulderY) / timeDiff) / timeDiff;
                    jerk = (acceleration - prevAcceleration) / timeDiff;
                }
            }
        }

        PoseFeatures f = new PoseFeatures();
        f.height = height;
        f.angle = angle;
        f.velocityY = velocityY;
        f.velocityX = velocityX;
        f.acceleration = acceleration;
        f.jerk = jerk;
        f.midShoulderY = midShoulderY;
        f.midShoulderX = midShoulderX;
        f.midHipY = midHipY;
        f.midHipX = midHipX;
        f.aspectRatio = aspectRatio;
        f.shoulderToHipDistance = shoulderToHip;
        f.hipToFeetDistance = hipToFeet;
        f.timestamp = now;

        prevPoses.add(f);
        if (prevPoses.size() > MAX_POSE_HISTORY) prevPoses.remove(0);
        return f;
    }
}
