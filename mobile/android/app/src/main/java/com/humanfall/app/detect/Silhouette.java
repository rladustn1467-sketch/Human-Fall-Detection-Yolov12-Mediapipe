package com.humanfall.app.detect;

import android.graphics.Bitmap;
import java.io.ByteArrayOutputStream;
import java.util.List;

/**
 * Privacy photo for a fall, following utils/silhouette.py: every detected person is painted solid gray and the
 * background is blurred, so faces and clothes cannot be seen. The original frame is never encoded or kept: if any
 * person cannot be masked reliably, no photo is made (the fall is still sent, without a photo).
 *
 * Differences from the PC: the masks come from the same Pose Landmarker run that found the people (the PC runs a
 * second MediaPipe pass on each person crop), and the background blur is a down/up-scale blur instead of OpenCV's
 * Gaussian blur (similar strength at 640 px).
 */
final class Silhouette {
    static final int MAX_SIDE = 640;          // utils/silhouette.py 와 같음
    static final int JPEG_QUALITY = 80;
    static final int COLOR = 0xFF3C3C3C;      // (60, 60, 60)
    static final int BLUR_FACTOR = 10;        // 640px 기준 가우시안 sigma 4 정도의 흐림

    /**
     * Scales a frame so its long side is at most MAX_SIDE (always a new bitmap). Width and height are made multiples
     * of 4: MediaPipe cannot hand out the person mask of a frame whose rows are not 4-byte aligned (it throws, e.g.
     * for a 425-pixel-wide frame), so every analysed frame has an aligned size (at most 3 pixels narrower).
     */
    static Bitmap shrink(Bitmap frame) {
        int w = frame.getWidth(), h = frame.getHeight();
        double scale = Math.min(1.0, MAX_SIDE / (double) Math.max(w, h));
        int tw = Math.max(4, (int) (w * scale) / 4 * 4), th = Math.max(4, (int) (h * scale) / 4 * 4);
        if (tw == w && th == h) return frame.copy(Bitmap.Config.ARGB_8888, false);
        return Bitmap.createScaledBitmap(frame, tw, th, true);
    }

    /**
     * @param frame frame the people were found in (masks have the same size)
     * @param boxes person boxes in frame pixels
     * @param masks the person masks of those boxes (same order)
     * @return JPEG bytes, or null when a person could not be masked
     */
    static byte[] render(Bitmap frame, List<int[]> boxes, List<float[]> masks, int maskW, int maskH) {
        int w = frame.getWidth(), h = frame.getHeight();
        if (boxes.isEmpty() || masks.size() != boxes.size() || maskW != w || maskH != h) return null;
        for (int i = 0; i < boxes.size(); i++) {
            if (!FrameMath.maskRatioOk(masks.get(i), w, h, boxes.get(i))) return null;
        }
        boolean[] paint = FrameMath.dilatedMask(masks.toArray(new float[0][]), w, h);

        // 흐린 배경에서 시작하므로 원본 픽셀은 그대로 남지 않음
        Bitmap small = Bitmap.createScaledBitmap(frame, Math.max(1, w / BLUR_FACTOR), Math.max(1, h / BLUR_FACTOR), true);
        Bitmap blurred = Bitmap.createScaledBitmap(small, w, h, true);
        small.recycle();
        int[] px = new int[w * h];
        blurred.getPixels(px, 0, w, 0, 0, w, h);
        blurred.recycle();
        for (int i = 0; i < px.length; i++) if (paint[i]) px[i] = COLOR;
        Bitmap out = Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888);
        ByteArrayOutputStream jpeg = new ByteArrayOutputStream();
        boolean ok = out.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, jpeg);
        out.recycle();
        return ok ? jpeg.toByteArray() : null;
    }
}
