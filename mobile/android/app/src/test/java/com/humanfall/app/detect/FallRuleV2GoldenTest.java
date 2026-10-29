package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Assume;
import org.junit.Test;

/**
 * The Java fall rule v2 (V2Features + FallRuleV2) must give the same per-frame inputs and the same alarm as the
 * Python code (tools/urfall_features.py + fall_logic/v2.py) on recorded pose logs.
 * Golden data: tools/export_fall_v2_golden.py. The small file is in git; the file with every recorded video
 * (161 videos) is checked when the environment variable FALL_V2_GOLDEN_ALL points to it.
 * The app's log-only wrapper V2Shadow (used by FallPipeline) is replayed next to it and must agree.
 */
public class FallRuleV2GoldenTest {
    private static final double EPS = 1e-9;
    private static final String[] NAMES = {"A1", "H3", "B1", "C1"};

    private static Double opt(JSONArray a, int i) throws Exception {
        return a.isNull(i) ? null : a.getDouble(i);
    }

    private static void close(String what, Double expected, Double actual) {
        if (expected == null) {
            assertNull(what, actual);
            return;
        }
        if (actual == null) fail(what + ": expected " + expected + ", got null");
        assertEquals(what, expected, actual, EPS * Math.max(1.0, Math.abs(expected)));
    }

    /** Replays every case; returns {frames, alarms}. */
    private static int[] replay(String json) throws Exception {
        JSONArray cases = new JSONObject(json).getJSONArray("cases");
        int frames = 0, alarms = 0;
        for (int c = 0; c < cases.length(); c++) {
            JSONObject seq = cases.getJSONObject(c);
            String name = seq.getString("name");
            V2Features features = new V2Features(seq.getDouble("fps"));
            FallRuleV2 rule = new FallRuleV2();
            V2Shadow shadow = new V2Shadow(seq.getDouble("fps"));
            JSONArray fs = seq.getJSONArray("frames"), ex = seq.getJSONArray("expected");
            for (int i = 0; i < fs.length(); i++) {
                JSONObject f = fs.getJSONObject(i);
                List<int[]> boxes = new ArrayList<>();
                List<double[][]> lms = new ArrayList<>();
                JSONArray b = f.getJSONArray("boxes"), l = f.getJSONArray("lms");
                for (int k = 0; k < b.length(); k++) {
                    JSONArray bk = b.getJSONArray(k);
                    boxes.add(new int[]{bk.getInt(0), bk.getInt(1), bk.getInt(2), bk.getInt(3)});
                    if (l.isNull(k)) {
                        lms.add(null);
                        continue;
                    }
                    JSONArray lk = l.getJSONArray(k);
                    double[][] p = new double[lk.length()][4];
                    for (int j = 0; j < lk.length(); j++) {
                        JSONArray q = lk.getJSONArray(j);
                        p[j][0] = q.getDouble(0);
                        p[j][1] = q.getDouble(1);
                        p[j][3] = q.getDouble(2);      // [x, y, z(=0), visibility]
                    }
                    lms.add(p);
                }
                V2Features.Frame got = features.update(boxes, lms);
                JSONArray e = ex.getJSONArray(i);
                Double[] actual = {got.a1, got.h3, got.b1, got.c1};
                for (int k = 0; k < 4; k++) close(name + " frame " + i + " " + NAMES[k], opt(e, k), actual[k]);
                boolean fired = rule.update(f.getDouble("t"), got.a1, got.h3, got.b1, got.c1) != null;
                V2Shadow.Result sh = shadow.update(f.getDouble("t"), boxes, lms);
                Double[] viaShadow = {sh.a1, sh.h3, sh.b1, sh.c1};
                for (int k = 0; k < 4; k++) close(name + " frame " + i + " shadow " + NAMES[k], opt(e, k), viaShadow[k]);
                assertEquals(name + " frame " + i + " shadow fired", fired, sh.fired);
                frames++;
            }
            Double expected = seq.isNull("alarm") ? null : seq.getDouble("alarm");
            close(name + " alarm", expected, rule.alarm());
            close(name + " shadow alarm", expected, shadow.alarm());
            if (expected != null) alarms++;
        }
        return new int[]{frames, alarms};
    }

    @Test
    public void javaPortMatchesPythonOnRecordedVideos() throws Exception {
        String text;
        try (InputStream in = getClass().getClassLoader().getResourceAsStream("fall_rule_v2_golden.json")) {
            text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        int[] r = replay(text);
        assertTrue("frames", r[0] > 1000);
        assertTrue("both alarms and no alarms covered", r[1] >= 2 && r[1] < 8);
    }

    @Test
    public void javaPortMatchesPythonOnEveryRecordedVideo() throws Exception {
        String path = System.getenv("FALL_V2_GOLDEN_ALL");
        Assume.assumeTrue("FALL_V2_GOLDEN_ALL not set", path != null && !path.isEmpty());
        int[] r = replay(new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8));
        System.out.println("FallRuleV2 전체 비교: 프레임 " + r[0] + ", 알림 " + r[1]);
    }

    @Test
    public void shadowErrorTurnsOnlyTheShadowOff() {
        V2Shadow shadow = new V2Shadow(30);
        List<int[]> boxes = new ArrayList<>();
        List<double[][]> lms = new ArrayList<>();
        boxes.add(new int[]{0, 0, 100, 200});
        lms.add(new double[3][4]);   // 관절 3개뿐: 계산 중 오류
        try {
            shadow.update(0.0, boxes, lms);
            fail("expected an error");
        } catch (RuntimeException expected) {
            // FallPipeline 이 잡아서 기록만 남김
        }
        assertTrue(shadow.broken());
        assertNull(shadow.update(0.1, new ArrayList<>(), new ArrayList<>()));
        assertNull(shadow.alarm());
    }

    @Test
    public void defaultsAreTheChosenValues() {
        FallRuleV2.Params p = FallRuleV2.Params.DEFAULT;
        assertEquals(40.0, p.lowAngle, 0);
        assertEquals(0.3, p.lowHead, 0);
        assertEquals(1.5, p.wideBox, 0);
        assertEquals(2.0, p.dropSpeed, 0);
        assertTrue(p.dropAfterWide);
        assertEquals(3, p.dropFrames);
        assertEquals(1.0, p.dropWindow, 0);
        assertEquals(1.0, p.staySeconds, 0);
        assertEquals(1.0, p.gapSeconds, 0);
    }
}
