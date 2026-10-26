package com.humanfall.app.detect;

import android.content.Context;
import android.graphics.Bitmap;
import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.ByteBufferExtractor;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark;
import com.google.mediapipe.tasks.core.BaseOptions;
import com.google.mediapipe.tasks.core.Delegate;
import com.google.mediapipe.tasks.vision.core.RunningMode;
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker;
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarkerResult;
import java.io.Closeable;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.ArrayList;
import java.util.List;

/**
 * MediaPipe Pose Landmarker on the phone (same official model as the android/ test app): up to two people per
 * frame, 33 landmarks each (fractions of the frame), and a person mask per person for the silhouette photo.
 * Video mode: frames must come with increasing timestamps; the model tracks people between frames.
 */
final class PoseDetector implements Closeable {
    static final String MODEL = "pose_landmarker_full.task";

    static final class Frame {
        final List<double[][]> poses = new ArrayList<>();
        final List<float[]> masks = new ArrayList<>();
        int maskWidth, maskHeight;
    }

    private final PoseLandmarker landmarker;
    private long lastTimestamp = -1;

    PoseDetector(Context context) {
        PoseLandmarker.PoseLandmarkerOptions options = PoseLandmarker.PoseLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath(MODEL).setDelegate(Delegate.CPU).build())
                .setRunningMode(RunningMode.VIDEO)
                .setNumPoses(2)
                .setMinPoseDetectionConfidence(0.5f)   // PC 의 MediaPipe Pose 와 같은 기준
                .setMinPosePresenceConfidence(0.5f)
                .setMinTrackingConfidence(0.5f)
                .setOutputSegmentationMasks(true)
                .build();
        landmarker = PoseLandmarker.createFromOptions(context, options);
    }

    Frame detect(Bitmap bitmap, long timestampMs) {
        long ts = Math.max(timestampMs, lastTimestamp + 1);   // 영상 모드는 시각이 계속 커져야 함
        lastTimestamp = ts;
        MPImage image = new BitmapImageBuilder(bitmap).build();
        PoseLandmarkerResult r = landmarker.detectForVideo(image, ts);
        Frame f = new Frame();
        for (List<NormalizedLandmark> person : r.landmarks()) {
            double[][] lm = new double[person.size()][4];
            for (int i = 0; i < person.size(); i++) {
                NormalizedLandmark l = person.get(i);
                lm[i][0] = l.x();
                lm[i][1] = l.y();
                lm[i][2] = l.z();
                lm[i][3] = l.visibility().orElse(0f);
            }
            f.poses.add(lm);
        }
        if (r.segmentationMasks().isPresent()) {
            for (MPImage m : r.segmentationMasks().get()) {
                ByteBuffer buf = ByteBufferExtractor.extract(m);
                FloatBuffer fb = buf.order(ByteOrder.nativeOrder()).asFloatBuffer();
                float[] values = new float[fb.remaining()];
                fb.get(values);
                f.masks.add(values);
                f.maskWidth = m.getWidth();
                f.maskHeight = m.getHeight();
            }
        }
        return f;
    }

    @Override
    public void close() {
        landmarker.close();
    }
}
