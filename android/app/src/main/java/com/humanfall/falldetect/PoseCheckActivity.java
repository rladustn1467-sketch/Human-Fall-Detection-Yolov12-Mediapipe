package com.humanfall.falldetect;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.widget.ScrollView;
import android.widget.TextView;

import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark;
import com.google.mediapipe.tasks.core.BaseOptions;
import com.google.mediapipe.tasks.core.Delegate;
import com.google.mediapipe.tasks.vision.core.RunningMode;
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker;
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarkerResult;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * Stage-1 check: does MediaPipe Pose Landmarker initialize on this device (emulator) and return
 * real landmarks? Reads one photo from the app's external files dir, runs the landmarker once in
 * IMAGE mode on the CPU, and writes the result to pose_check_result.json in the same dir.
 *
 * Put the photo first:  adb push photo.jpg /sdcard/Android/data/com.humanfall.falldetect/files/pose_check.jpg
 * Read the result:      adb pull /sdcard/Android/data/com.humanfall.falldetect/files/pose_check_result.json
 */
public class PoseCheckActivity extends Activity {
    private static final String TAG = "PoseCheck";
    // app/src/main/assets 에 넣는 공식 모델 (README.md 참고)
    private static final String MODEL_ASSET = "pose_landmarker_full.task";
    private static final String INPUT_NAME = "pose_check.jpg";
    private static final String OUTPUT_NAME = "pose_check_result.json";
    private static final int MAX_POSES = 2;

    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        status = new TextView(this);
        status.setTextSize(18);
        status.setPadding(32, 32, 32, 32);
        status.setText("MediaPipe 검사 중...");
        ScrollView scroll = new ScrollView(this);
        scroll.addView(status);
        setContentView(scroll);

        // 모델 실행은 화면 스레드가 아닌 곳에서
        new Thread(() -> {
            String summary = runCheck();
            runOnUiThread(() -> status.setText(summary));
        }, "pose-check").start();
    }

    private String runCheck() {
        JSONObject out = new JSONObject();
        StringBuilder summary = new StringBuilder();
        File dir = getExternalFilesDir(null);
        try {
            out.put("device", Build.MODEL);
            out.put("sdk_int", Build.VERSION.SDK_INT);
            out.put("supported_abis", new JSONArray(Build.SUPPORTED_ABIS));
            out.put("os_arch", System.getProperty("os.arch"));
            out.put("model_asset", MODEL_ASSET);
            summary.append("기기: ").append(Build.MODEL).append(" / API ").append(Build.VERSION.SDK_INT)
                    .append("\nABI: ").append(String.join(", ", Build.SUPPORTED_ABIS)).append('\n');

            File input = new File(dir, INPUT_NAME);
            out.put("input", input.getAbsolutePath());
            Bitmap bitmap = BitmapFactory.decodeFile(input.getAbsolutePath());
            if (bitmap == null) {
                throw new IllegalStateException("입력 사진이 없습니다: " + input.getAbsolutePath());
            }
            out.put("image_width", bitmap.getWidth());
            out.put("image_height", bitmap.getHeight());

            long start = SystemClock.elapsedRealtime();
            BaseOptions baseOptions = BaseOptions.builder()
                    .setModelAssetPath(MODEL_ASSET)
                    .setDelegate(Delegate.CPU)
                    .build();
            PoseLandmarker.PoseLandmarkerOptions options = PoseLandmarker.PoseLandmarkerOptions.builder()
                    .setBaseOptions(baseOptions)
                    .setRunningMode(RunningMode.IMAGE)
                    .setNumPoses(MAX_POSES)
                    .build();
            PoseLandmarker landmarker = PoseLandmarker.createFromOptions(this, options);
            long initialized = SystemClock.elapsedRealtime();
            try {
                MPImage image = new BitmapImageBuilder(bitmap).build();
                PoseLandmarkerResult result = landmarker.detect(image);
                long detected = SystemClock.elapsedRealtime();

                JSONArray poses = new JSONArray();
                for (List<NormalizedLandmark> pose : result.landmarks()) {
                    JSONArray points = new JSONArray();
                    for (NormalizedLandmark lm : pose) {
                        JSONArray p = new JSONArray();
                        p.put((double) lm.x());
                        p.put((double) lm.y());
                        p.put((double) lm.z());
                        p.put(lm.visibility().isPresent() ? (double) lm.visibility().get() : JSONObject.NULL);
                        points.put(p);
                    }
                    poses.put(points);
                }
                out.put("init_ms", initialized - start);
                out.put("detect_ms", detected - initialized);
                out.put("pose_count", poses.length());
                out.put("poses", poses);
                out.put("ok", true);
                summary.append("초기화: ").append(initialized - start).append(" ms\n")
                        .append("추론: ").append(detected - initialized).append(" ms\n")
                        .append("감지된 사람: ").append(poses.length()).append("명\n");
                if (poses.length() > 0) {
                    JSONArray nose = poses.getJSONArray(0).getJSONArray(0);
                    summary.append("첫 사람 관절 수: ").append(poses.getJSONArray(0).length())
                            .append("\n코(0번): x=").append(nose.getDouble(0)).append(", y=").append(nose.getDouble(1));
                }
            } finally {
                landmarker.close();
            }
        } catch (Throwable e) {
            Log.e(TAG, "pose check failed", e);
            try {
                out.put("ok", false);
                out.put("error", e.toString());
            } catch (Exception ignored) {
                // JSON 기록 실패는 무시 (로그에 오류가 남음)
            }
            summary.append("실패: ").append(e);
        }

        File output = new File(dir, OUTPUT_NAME);
        try (FileOutputStream fos = new FileOutputStream(output)) {
            fos.write(out.toString().getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            Log.e(TAG, "could not write " + output, e);
        }
        Log.i(TAG, "SUMMARY " + summary.toString().replace("\n", " | "));
        return summary.toString();
    }
}
