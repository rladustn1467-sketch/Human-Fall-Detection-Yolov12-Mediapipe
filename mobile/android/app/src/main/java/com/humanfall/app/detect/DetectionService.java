package com.humanfall.app.detect;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.util.Size;
import androidx.annotation.Nullable;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.resolutionselector.ResolutionSelector;
import androidx.camera.core.resolutionselector.ResolutionStrategy;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.core.app.NotificationCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.LifecycleService;
import com.google.common.util.concurrent.ListenableFuture;
import com.humanfall.app.BuildConfig;
import com.humanfall.app.R;
import java.io.File;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

/**
 * Keeps this phone working as a detection device while it is connected to a home: status signal every minute,
 * camera frames → fall decision → fall with silhouette photo. Runs as a foreground service (visible notification),
 * because Android only lets apps use the camera in the background that way.
 *
 * The camera follows the on/off set in the family app (or on this phone): off = the camera is released and no
 * frame is analysed. If the device is deleted in the app (401), the service stops itself.
 *
 * Emulator check (debug builds only): with the extra MOCK_FRAMES_DIR, images in that folder are fed through the very
 * same pipeline instead of the camera, so pairing → decision → incident → photo can be tested without a real phone.
 * With MOCK_FPS as well, the folder is one recorded video: its frames go through once, one after another, with the
 * video's own times (frame number in the file name / fps; frames left out of the folder = dropped frames), so the
 * current rule and v2 (log only) can be compared on the emulator.
 */
public class DetectionService extends LifecycleService {
    static final String TAG = "DetectionService";
    public static final String EXTRA_MOCK_FRAMES_DIR = "mock_frames_dir";       // debug 빌드만
    public static final String EXTRA_HEARTBEAT_SECONDS = "heartbeat_seconds";   // debug 빌드만
    public static final String EXTRA_MOCK_FPS = "mock_fps";                     // debug 빌드만 (녹화 영상 한 번 재생)
    public static final String ACTION_NUDGE = "com.humanfall.app.detect.NUDGE"; // 상태 신호를 바로 한 번
    static final String CHANNEL = "detect";
    static final int NOTIFICATION_ID = 41;

    private final Handler main = new Handler(Looper.getMainLooper());
    private ScheduledExecutorService linkExec;
    private ExecutorService analysisExec;
    private ExecutorService sendExec;
    private ScheduledExecutorService mockExec;
    private ProcessCameraProvider provider;
    private PoseDetector detector;
    private FallPipeline pipeline;
    private DeviceLink link;
    private String mockDir;
    private float mockFps;
    private int heartbeatOverride;
    private boolean cameraWanted;
    private volatile boolean firstFrameReported;   // 카메라가 켜진 뒤 첫 프레임에서 상태 신호를 한 번 바로 보냄
    private final FrameRate rate = new FrameRate();

    /** Start (or nudge) the service. Needs the camera permission: Android refuses a camera service without it. */
    public static boolean start(Context context, @Nullable Intent extras) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            DetectorRuntime.STATE.camera = "permission";
            return false;
        }
        Intent i = new Intent(context, DetectionService.class);
        if (extras != null) i.putExtras(extras);
        ContextCompat.startForegroundService(context, i);
        return true;
    }

    public static void stop(Context context) {
        context.stopService(new Intent(context, DetectionService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        link = DetectorRuntime.link(this);
        linkExec = Executors.newSingleThreadScheduledExecutor();
        analysisExec = Executors.newSingleThreadExecutor();
        sendExec = Executors.newSingleThreadExecutor();
        createChannel();
        startInForeground(getString(R.string.detect_notice_starting));
        DetectorRuntime.STATE.serviceRunning = true;
        BootReceiver.clear(this);   // 감지를 다시 시작함: '감지가 멈춰 있어요' 알림 지움
    }

    @Override
    public int onStartCommand(@Nullable Intent intent, int flags, int startId) {
        super.onStartCommand(intent, flags, startId);
        if (intent != null && BuildConfig.DEBUG) {
            if (intent.hasExtra(EXTRA_MOCK_FRAMES_DIR)) mockDir = intent.getStringExtra(EXTRA_MOCK_FRAMES_DIR);
            if (intent.hasExtra(EXTRA_HEARTBEAT_SECONDS)) heartbeatOverride = intent.getIntExtra(EXTRA_HEARTBEAT_SECONDS, 0);
            if (intent.hasExtra(EXTRA_MOCK_FPS)) mockFps = intent.getFloatExtra(EXTRA_MOCK_FPS, 0f);
        }
        if (!link.isPaired()) {
            stopSelf();
            return START_NOT_STICKY;
        }
        beatNow();                // 시작·재요청 때 바로 상태 신호 → 카메라 켜기/끄기 결정
        return START_STICKY;      // 시스템이 정리해도 다시 시작
    }

    // ---- 상태 신호 (예약은 항상 하나만) ----
    private ScheduledFuture<?> nextBeat;

    private synchronized void beatNow() {
        if (linkExec.isShutdown()) return;
        if (nextBeat != null) nextBeat.cancel(false);
        nextBeat = linkExec.schedule(this::beat, 0, TimeUnit.SECONDS);
    }

    private void beat() {
        int next = link.heartbeat(DetectorRuntime.cameraOk());
        if (heartbeatOverride > 0) next = heartbeatOverride;
        main.post(this::followServer);
        synchronized (this) {
            if (!linkExec.isShutdown()) nextBeat = linkExec.schedule(this::beat, next, TimeUnit.SECONDS);
        }
    }

    /** Main thread: camera on/off as the server says; stop when the device was deleted in the app. */
    private void followServer() {
        if (!link.isPaired()) {
            Log.i(TAG, "기기 연결이 없어 감지를 멈춤 (해제됨=" + link.isRevoked() + ")");
            stopCamera();
            stopSelf();
            return;
        }
        if (link.enabled) startCamera();   // 이 기기에서 정한 값대로 (서버 값으로 켜지지 않음)
        else stopCamera();
        updateNotification();
    }

    // ---- 카메라 ----
    private void startCamera() {
        if (cameraWanted) return;
        cameraWanted = true;
        firstFrameReported = false;
        rate.clear();
        DetectorRuntime.STATE.fps = Double.NaN;
        DetectorRuntime.STATE.frameMs = Double.NaN;
        DetectorRuntime.STATE.camera = "starting";
        DetectorRuntime.STATE.cameraError = null;
        if (detector == null) {
            try {
                detector = new PoseDetector(this);
            } catch (RuntimeException e) {
                Log.e(TAG, "자세 인식 모델을 불러오지 못함", e);
                DetectorRuntime.STATE.camera = "error";
                DetectorRuntime.STATE.cameraError = "model";
                cameraWanted = false;
                return;
            }
            pipeline = new FallPipeline(detector, this::onFall);
        }
        if (BuildConfig.DEBUG && mockDir != null) {
            startMockFrames();
            return;
        }
        ListenableFuture<ProcessCameraProvider> future = ProcessCameraProvider.getInstance(this);
        future.addListener(() -> {
            try {
                provider = future.get();
                if (!cameraWanted) return;
                ImageAnalysis analysis = new ImageAnalysis.Builder()
                        .setResolutionSelector(new ResolutionSelector.Builder().setResolutionStrategy(
                                new ResolutionStrategy(new Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)).build())
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)   // 밀린 프레임은 버리고 최신만
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                        .build();
                analysis.setAnalyzer(analysisExec, this::analyze);
                CameraSelector selector = provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)
                        ? CameraSelector.DEFAULT_BACK_CAMERA : CameraSelector.DEFAULT_FRONT_CAMERA;
                provider.unbindAll();
                provider.bindToLifecycle(this, selector, analysis);
                DetectorRuntime.STATE.camera = "running";
                Log.i(TAG, "카메라 감지 시작");
            } catch (Exception e) {
                Log.e(TAG, "카메라를 사용할 수 없음", e);
                DetectorRuntime.STATE.camera = "error";
                DetectorRuntime.STATE.cameraError = e.getClass().getSimpleName();
                cameraWanted = false;
            }
            updateNotification();
        }, ContextCompat.getMainExecutor(this));
    }

    private void stopCamera() {
        boolean was = cameraWanted;
        cameraWanted = false;
        if (provider != null) provider.unbindAll();
        if (mockExec != null) {
            mockExec.shutdownNow();
            mockExec = null;
        }
        DetectorRuntime.STATE.camera = link.isPaired() && !link.enabled ? "off" : "none";
        if (was) Log.i(TAG, "카메라 감지 멈춤 (카메라 해제)");
    }

    private void analyze(ImageProxy proxy) {
        try {
            if (!cameraWanted) return;
            Bitmap bmp = proxy.toBitmap();
            int rotation = proxy.getImageInfo().getRotationDegrees();
            if (rotation != 0) {
                Matrix m = new Matrix();
                m.postRotate(rotation);
                Bitmap rotated = Bitmap.createBitmap(bmp, 0, 0, bmp.getWidth(), bmp.getHeight(), m, true);
                bmp.recycle();
                bmp = rotated;
            }
            runPipeline(bmp, null, System.currentTimeMillis());
        } catch (RuntimeException e) {
            Log.e(TAG, "프레임 분석 실패", e);
        } finally {
            proxy.close();
        }
    }

    private void runPipeline(Bitmap bmp, @Nullable String label, long nowMs) {
        DetectorRuntime.State st = DetectorRuntime.STATE;
        st.lastFrameAt = System.currentTimeMillis();
        st.frames++;
        if (!firstFrameReported) {
            firstFrameReported = true;
            beatNow();   // 카메라가 실제로 영상을 받기 시작했음을 서버에 바로 알림
            // 640 을 넘으면 분석 전에 줄임 (줄이는 방법이 PC 평가 도구와 달라 판정이 조금 달라질 수 있음, docs/fall_rule_v2.md)
            st.frameSize = bmp.getWidth() + "x" + bmp.getHeight();
            Log.i(TAG, "첫 프레임 크기 " + st.frameSize
                    + (Math.max(bmp.getWidth(), bmp.getHeight()) > Silhouette.MAX_SIDE ? " (줄여서 분석)" : ""));
        }
        FallPipeline.Stats s;
        long began = System.nanoTime();
        try {
            s = pipeline.process(bmp, nowMs);
        } catch (RuntimeException e) {
            // 프레임 한 장의 문제로 감지 전체가 멈추지 않게 그 프레임만 건너뜀
            Log.e(TAG, "프레임 처리 실패 (건너뜀)" + (label != null ? " file=" + label : ""), e);
            return;
        } finally {
            bmp.recycle();
        }
        st.persons = s.persons;
        // 실제로 분석한 속도 (카메라가 밀린 프레임을 버리므로 규칙이 보는 속도는 이것)
        boolean report = rate.add(System.currentTimeMillis(), (System.nanoTime() - began) / 1_000_000);
        st.fps = rate.fps();
        st.frameMs = rate.averageMs();
        if (report) {
            Log.i(TAG, String.format(java.util.Locale.ROOT, "처리 속도 %.1f장/초, 프레임당 %.0fms (최근 10초, 크기 %s)", st.fps, st.frameMs, st.frameSize));
        }
        if (label != null || s.fallInFrame || st.frames % 30 == 0 || (s.v2 != null && s.v2.fired)) {
            Log.i(TAG, "frame " + st.frames + (label != null ? " file=" + label : "") + " persons=" + s.persons + " posture=" + s.posture + " fall=" + s.fallInFrame + " new=" + s.newFalls
                    + " angle=" + s.angle + " aspect=" + s.aspectRatio + " brightened=" + s.brightened
                    + " t=" + nowMs / 1000.0 + " " + v2Text(s.v2));
        }
    }

    /** v2 (log only): its inputs and whether it fired on this frame. */
    private String v2Text(@Nullable V2Shadow.Result v) {
        if (v == null) return "v2=off";
        return "v2a1=" + v.a1 + " v2h3=" + v.h3 + " v2b1=" + v.b1 + " v2c1=" + v.c1 + " v2fire=" + v.fired;
    }

    /** Debug builds only: images from a folder instead of the camera, through the same pipeline. */
    private void startMockFrames() {
        File[] files = new File(mockDir).listFiles((d, n) -> n.toLowerCase().matches(".*\\.(jpg|jpeg|png)$"));
        if (files == null || files.length == 0) {
            Log.e(TAG, "시험용 사진을 읽을 수 없음: " + mockDir);
            DetectorRuntime.STATE.camera = "error";
            DetectorRuntime.STATE.cameraError = "mock: no images in " + mockDir;
            cameraWanted = false;
            return;
        }
        Arrays.sort(files);
        DetectorRuntime.STATE.camera = "mock";
        if (mockFps > 0) {
            startMockVideo(files);
            return;
        }
        Log.i(TAG, "시험용 사진 입력 시작 (" + files.length + "장, 카메라 대신)");
        mockExec = Executors.newSingleThreadScheduledExecutor();
        final int[] next = {0};
        mockExec.scheduleWithFixedDelay(() -> {
            if (!cameraWanted) return;
            File f = files[next[0]++ % files.length];
            Bitmap bmp = BitmapFactory.decodeFile(f.getAbsolutePath());
            if (bmp != null) analysisExec.execute(() -> runPipeline(bmp, f.getName(), System.currentTimeMillis()));
        }, 0, 300, TimeUnit.MILLISECONDS);
    }

    /**
     * Debug builds only: the folder is one recorded video (frames in name order). Each frame is analysed after the
     * previous one finished, at the video's own time (start + (number in the file name - 1) / fps, or its position
     * when the name has no number), once. At the end the first alert of the
     * current rule and v2's alarm (log only) are written, in seconds from the start of the video.
     */
    private void startMockVideo(File[] files) {
        Log.i(TAG, "시험용 영상 입력 시작 (" + files.length + "장, " + mockFps + " fps, 한 번만)");
        mockExec = Executors.newSingleThreadScheduledExecutor();
        mockExec.execute(() -> {
            long start = System.currentTimeMillis();
            double legacyFirst = Double.NaN;
            int done = 0;
            for (int i = 0; i < files.length && cameraWanted; i++) {
                File f = files[i];
                Bitmap bmp = BitmapFactory.decodeFile(f.getAbsolutePath());
                if (bmp == null) continue;
                String digits = f.getName().replaceAll("\\D", "");
                long at = start + Math.round((digits.isEmpty() ? i : Long.parseLong(digits) - 1) * 1000.0 / mockFps);
                long fallsBefore = DetectorRuntime.STATE.lastFallAt;
                try {
                    analysisExec.submit(() -> runPipeline(bmp, f.getName(), at)).get();
                } catch (Exception e) {
                    Log.w(TAG, "시험용 영상 중단", e);
                    return;
                }
                done++;
                if (Double.isNaN(legacyFirst) && DetectorRuntime.STATE.lastFallAt != fallsBefore) legacyFirst = (at - start) / 1000.0;
            }
            List<Double> v2 = pipeline.v2Alarms();
            Log.i(TAG, "시험용 영상 끝: 프레임 " + done + "/" + files.length + " legacy_first=" + (Double.isNaN(legacyFirst) ? "none" : legacyFirst)
                    + " v2_alarm=" + (v2.isEmpty() ? "none" : (v2.get(0) - start / 1000.0)) + " v2_alarms=" + v2.size());
        });
    }

    // ---- 낙상 전송 ----
    private void onFall(String eventId, byte[] jpeg) {
        DetectorRuntime.STATE.lastFallAt = System.currentTimeMillis();
        sendExec.execute(() -> {
            try {
                JSONObject r = link.sendFallOrKeep(eventId, jpeg);
                DetectorRuntime.STATE.lastFallResult = r == null ? "kept" : (r.optBoolean("image_saved") ? "sent+photo" : "sent");
                Log.i(TAG, "낙상 전송 event=" + eventId.substring(0, 8) + " 결과=" + (r == null ? "보관(네트워크)" : r.toString()));
            } catch (DeviceLink.Revoked e) {
                DetectorRuntime.STATE.lastFallResult = "revoked";
                Log.w(TAG, "기기 연결이 해제돼 보내지 않음");
                main.post(this::followServer);
            } catch (RuntimeException e) {
                DetectorRuntime.STATE.lastFallResult = "error";
                Log.e(TAG, "낙상 전송 실패", e);
            }
        });
    }

    // ---- 알림 ----
    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, getString(R.string.detect_channel), NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, DetectorActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new NotificationCompat.Builder(this, CHANNEL)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(getString(R.string.detect_title))
                .setContentText(text)
                .setOngoing(true)
                .setContentIntent(pi)
                .build();
    }

    private void startInForeground(String text) {
        int type = Build.VERSION.SDK_INT >= 30 ? ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA : 0;
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(text), type);
    }

    private void updateNotification() {
        String c = DetectorRuntime.STATE.camera;
        String text = !link.enabled ? getString(R.string.detect_notice_off)
                : "error".equals(c) ? getString(R.string.detect_notice_camera_error)
                : getString(R.string.detect_notice_on);
        getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, notification(text));
    }

    @Override
    public void onDestroy() {
        stopCamera();
        DetectorRuntime.STATE.serviceRunning = false;
        DetectorRuntime.STATE.camera = "none";
        linkExec.shutdownNow();
        if (detector != null) {
            final PoseDetector d = detector;
            analysisExec.execute(d::close);   // 분석 중인 프레임이 끝난 뒤 닫음
        }
        analysisExec.shutdown();
        sendExec.shutdown();              // 보내는 중인 낙상은 끝까지 보냄
        super.onDestroy();
    }
}
