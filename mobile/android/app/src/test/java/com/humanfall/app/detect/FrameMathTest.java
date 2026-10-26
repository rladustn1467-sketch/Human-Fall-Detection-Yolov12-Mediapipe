package com.humanfall.app.detect;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

/** Phone pixel math compared with the PC's utils/low_light.py and utils/silhouette.py values. */
public class FrameMathTest {
    private static int[] pick(int[] lut) {
        return new int[]{lut[0], lut[1], lut[10], lut[50], lut[100], lut[200], lut[255]};
    }

    @Test
    public void gammaCurveMatchesThePc() {
        // 기대값: utils/low_light.py 의 LUT (numpy, 같은 밝기)
        assertArrayEquals(new int[]{0, 20, 58, 121, 166, 228, 255}, pick(FrameMath.gammaLut(40.0)));
        assertArrayEquals(new int[]{0, 6, 31, 88, 138, 217, 255}, pick(FrameMath.gammaLut(70.0)));
        assertArrayEquals(new int[]{0, 21, 59, 122, 167, 228, 255}, pick(FrameMath.gammaLut(5.0)));
        assertNull(FrameMath.gammaLut(150.0));                              // 이미 밝으면 바꾸지 않음
    }

    @Test
    public void brightnessUsesOpenCvGrayWeights() {
        int argb = 0xFF000000 | (30 << 16) | (200 << 8) | 10;              // OpenCV BGR (10, 200, 30) → 회색 128
        assertEquals(127.51, FrameMath.brightness(new int[]{argb, argb}), 1e-9);
    }

    @Test
    public void lowLightHysteresis() {
        FrameMath.LowLight ll = new FrameMath.LowLight();
        int dark = 0xFF282828, mid = 0xFF575757, bright = 0xFF707070;      // 40, 87, 112
        int[] px = {dark, dark};
        assertTrue(ll.process(px));
        assertTrue((px[0] & 0xff) > 40);                                    // 밝아짐
        assertTrue(ll.process(new int[]{mid}));                             // 87: 해제 기준(95)보다 어두워 계속 보정
        assertFalse(ll.process(new int[]{bright}));                         // 112 > 95: 보정 해제
        assertFalse(ll.process(new int[]{mid}));                            // 87 > 80: 다시 켜지지 않음
    }

    @Test
    public void maskRatioAndDilation() {
        int w = 40, h = 40;
        float[] mask = new float[w * h];
        for (int y = 10; y < 30; y++) for (int x = 15; x < 25; x++) mask[y * w + x] = 0.9f;   // 사람 10×20
        assertTrue(FrameMath.maskRatioOk(mask, w, h, new int[]{15, 10, 25, 30}));
        assertFalse(FrameMath.maskRatioOk(new float[w * h], w, h, new int[]{15, 10, 25, 30}));  // 비어 있음
        float[] full = new float[w * h];
        java.util.Arrays.fill(full, 1f);
        assertFalse(FrameMath.maskRatioOk(full, w, h, new int[]{15, 10, 25, 30}));            // 90% 넘음
        assertFalse(FrameMath.maskRatioOk(mask, w, h, new int[]{0, 0, 5, 5}));                // 너무 작은 상자
        boolean[] d = FrameMath.dilatedMask(new float[][]{mask}, w, h);
        assertTrue(d[10 * w + 11]);                                         // 4픽셀 넓어짐
        assertFalse(d[10 * w + 10]);                                        // 5픽셀은 아님
        assertTrue(d[6 * w + 20]);
        assertFalse(d[5 * w + 20]);
    }

    @Test
    public void poseBridgeMakesBoxAndBoxRelativeLandmarks() {
        double[][] p = new double[33][4];
        for (int i = 0; i < 33; i++) {
            p[i][0] = 0.25 + 0.5 * i / 32.0;   // 가로로 누운 사람: x 0.25~0.75
            p[i][1] = i % 3 == 0 ? 0.45 : i % 3 == 1 ? 0.60 : 0.52;   // 몸 두께 (y 0.45~0.60)
        }
        for (int i : PoseFeatures.KEY_POINTS) p[i][1] = 0.5 + 0.02 * (i % 2);   // 판정 관절은 거의 같은 높이 (누운 자세)
        List<double[][]> poses = new ArrayList<>();
        poses.add(p);
        poses.add(new double[0][]);           // 관절 없음 → 건너뜀
        PoseBridge.People r = PoseBridge.fromFrame(poses, 640, 480);
        assertEquals(1, r.boxes.size());
        assertEquals(List.of(0), r.sources);
        assertArrayEquals(new int[]{128, 208, 512, 296}, r.boxes.get(0));  // 범위(160~480, 216~288) + 10% 여유
        double[][] c = r.landmarks.get(0);
        assertEquals((0.25 * 640 - 128) / (512 - 128.0), c[0][0], 1e-12);
        assertEquals((0.5 * 480 - 208) / (296 - 208.0), c[0][1], 1e-12);
        // 누운 자세 → PC 와 같은 규칙으로 낙상 (각도 90도, 가로세로 비 < 1.5)
        LegacyFallLogic logic = new LegacyFallLogic();
        assertTrue(logic.update(0, r.boxes, r.landmarks).fallDetected);
    }
}
