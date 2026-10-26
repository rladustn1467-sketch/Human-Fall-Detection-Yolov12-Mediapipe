package com.humanfall.app.detect;

/**
 * Pixel math shared by the phone pipeline, kept free of Android classes so it runs in PC unit tests.
 *
 * Low light: same thresholds, hysteresis and gamma curve as utils/low_light.py. Not ported (needs OpenCV): the
 * NL-means denoise and CLAHE local contrast steps, so dark frames are brightened by the gamma curve only.
 * Silhouette: same mask threshold (0.5), per-person mask ratio check (0.05–0.90 of the box with 15% margin) and
 * 9×9 dilation as utils/silhouette.py; the masks come from the same Pose Landmarker run that found the people.
 */
public final class FrameMath {
    // utils/low_light.py 와 같은 값
    static final double DARK_THRESHOLD = 80;
    static final double BRIGHT_RELEASE_THRESHOLD = 95;
    static final double TARGET_BRIGHTNESS = 110;
    static final double MIN_GAMMA = 0.45;
    // utils/silhouette.py 와 같은 값
    static final double MASK_THRESHOLD = 0.5;
    static final double BOX_MARGIN = 0.15;
    static final double MIN_MASK_RATIO = 0.05;
    static final double MAX_MASK_RATIO = 0.90;
    static final int DILATE_RADIUS = 4;   // 9×9

    /** Mean grayscale brightness (0–255) of ARGB pixels, with OpenCV's BGR→gray weights. */
    public static double brightness(int[] argb) {
        if (argb.length == 0) return 0;
        double sum = 0;
        for (int c : argb) sum += 0.299 * ((c >> 16) & 0xff) + 0.587 * ((c >> 8) & 0xff) + 0.114 * (c & 0xff);
        return sum / argb.length;
    }

    /** Gamma lookup table that lifts the mean brightness toward TARGET (null = no change needed). */
    public static int[] gammaLut(double brightness) {
        double mean = Math.min(Math.max(brightness, 1.0), 254.0) / 255.0;
        double gamma = Math.log(TARGET_BRIGHTNESS / 255.0) / Math.log(mean);
        gamma = Math.max(MIN_GAMMA, Math.min(1.0, gamma));
        if (gamma >= 1.0) return null;
        int[] lut = new int[256];
        for (int i = 0; i < 256; i++) lut[i] = (int) (Math.pow(i / 255.0, gamma) * 255.0);   // numpy astype(uint8) 처럼 버림
        return lut;
    }

    public static void applyLut(int[] argb, int[] lut) {
        for (int i = 0; i < argb.length; i++) {
            int c = argb[i];
            argb[i] = (c & 0xff000000) | (lut[(c >> 16) & 0xff] << 16) | (lut[(c >> 8) & 0xff] << 8) | lut[c & 0xff];
        }
    }

    /** Low-light state with the same on/off hysteresis as LowLightEnhancer. */
    public static final class LowLight {
        public boolean active;

        /** Brightens dark frames in place. Returns true when the frame was changed. */
        public boolean process(int[] argb) {
            double b = brightness(argb);
            if (!active && b < DARK_THRESHOLD) active = true;
            else if (active && b > BRIGHT_RELEASE_THRESHOLD) active = false;
            if (!active) return false;
            int[] lut = gammaLut(b);
            if (lut == null) return false;
            applyLut(argb, lut);
            return true;
        }
    }

    /**
     * Person mask check, like SilhouetteRenderer: inside the person's box (+15% margin) the mask must cover between
     * 5% and 90%; otherwise the silhouette is not trusted and no photo is sent.
     */
    public static boolean maskRatioOk(float[] mask, int w, int h, int[] box) {
        int bw = box[2] - box[0], bh = box[3] - box[1];
        int mx = (int) (bw * BOX_MARGIN), my = (int) (bh * BOX_MARGIN);
        int x1 = Math.max(0, box[0] - mx), y1 = Math.max(0, box[1] - my);
        int x2 = Math.min(w, box[2] + mx), y2 = Math.min(h, box[3] + my);
        if (x2 - x1 < 10 || y2 - y1 < 10) return false;
        long on = 0, all = (long) (x2 - x1) * (y2 - y1);
        for (int y = y1; y < y2; y++) for (int x = x1; x < x2; x++) if (mask[y * w + x] > MASK_THRESHOLD) on++;
        double ratio = (double) on / all;
        return ratio >= MIN_MASK_RATIO && ratio <= MAX_MASK_RATIO;
    }

    /** Pixels to paint: any person's mask above 0.5, widened by a 9×9 square (edges must not leak). */
    public static boolean[] dilatedMask(float[][] masks, int w, int h) {
        boolean[] on = new boolean[w * h];
        for (float[] m : masks) for (int i = 0; i < on.length; i++) if (m[i] > MASK_THRESHOLD) on[i] = true;
        // 가로·세로로 나눠 넓힘 (정사각형 9×9 와 같음)
        boolean[] row = new boolean[w * h];
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                boolean v = false;
                for (int d = -DILATE_RADIUS; d <= DILATE_RADIUS && !v; d++) {
                    int xx = x + d;
                    if (xx >= 0 && xx < w && on[y * w + xx]) v = true;
                }
                row[y * w + x] = v;
            }
        }
        boolean[] out = new boolean[w * h];
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                boolean v = false;
                for (int d = -DILATE_RADIUS; d <= DILATE_RADIUS && !v; d++) {
                    int yy = y + d;
                    if (yy >= 0 && yy < h && row[yy * w + x]) v = true;
                }
                out[y * w + x] = v;
            }
        }
        return out;
    }
}
