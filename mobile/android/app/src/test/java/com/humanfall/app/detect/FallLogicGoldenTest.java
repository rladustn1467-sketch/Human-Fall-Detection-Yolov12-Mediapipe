package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/**
 * The Java fall logic must give the same decisions and features as the Python fall_logic (the PC detector's
 * decision part) for the same inputs. Golden data: tools/export_fall_logic_golden.py.
 */
public class FallLogicGoldenTest {
    private static final double EPS = 1e-9;
    private static final String[] KEYS = {"height", "angle", "velocity_y", "velocity_x", "acceleration", "jerk",
            "mid_shoulder_y", "mid_shoulder_x", "mid_hip_y", "mid_hip_x", "aspect_ratio",
            "shoulder_to_hip_distance", "hip_to_feet_distance"};

    private static double value(PoseFeatures f, String key) {
        switch (key) {
            case "height": return f.height;
            case "angle": return f.angle;
            case "velocity_y": return f.velocityY;
            case "velocity_x": return f.velocityX;
            case "acceleration": return f.acceleration;
            case "jerk": return f.jerk;
            case "mid_shoulder_y": return f.midShoulderY;
            case "mid_shoulder_x": return f.midShoulderX;
            case "mid_hip_y": return f.midHipY;
            case "mid_hip_x": return f.midHipX;
            case "aspect_ratio": return f.aspectRatio;
            case "shoulder_to_hip_distance": return f.shoulderToHipDistance;
            default: return f.hipToFeetDistance;
        }
    }

    private static List<Integer> ints(JSONArray a) throws Exception {
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i < a.length(); i++) out.add(a.getInt(i));
        return out;
    }

    @Test
    public void javaPortMatchesPythonFrameByFrame() throws Exception {
        String text;
        try (InputStream in = getClass().getClassLoader().getResourceAsStream("fall_logic_golden.json")) {
            text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        JSONArray cases = new JSONObject(text).getJSONArray("cases");
        int frames = 0, falls = 0, featureChecks = 0;
        for (int c = 0; c < cases.length(); c++) {
            JSONObject seq = cases.getJSONObject(c);
            LegacyFallLogic logic = new LegacyFallLogic();
            JSONArray fs = seq.getJSONArray("frames");
            for (int k = 0; k < fs.length(); k++) {
                JSONObject fr = fs.getJSONObject(k);
                String where = "seed " + seq.getInt("seed") + " frame " + k;
                List<int[]> boxes = new ArrayList<>();
                JSONArray jb = fr.getJSONArray("boxes");
                for (int i = 0; i < jb.length(); i++) {
                    JSONArray b = jb.getJSONArray(i);
                    boxes.add(new int[]{b.getInt(0), b.getInt(1), b.getInt(2), b.getInt(3)});
                }
                List<double[][]> lms = new ArrayList<>();
                JSONArray jl = fr.getJSONArray("landmarks");
                for (int i = 0; i < jl.length(); i++) {
                    if (jl.isNull(i)) { lms.add(null); continue; }
                    JSONArray pts = jl.getJSONArray(i);
                    double[][] lm = new double[pts.length()][4];
                    for (int p = 0; p < pts.length(); p++) {
                        JSONArray q = pts.getJSONArray(p);
                        for (int d = 0; d < 4; d++) lm[p][d] = q.getDouble(d);
                    }
                    lms.add(lm);
                }
                LegacyFallLogic.Result r = logic.update(fr.getDouble("now"), boxes, lms);
                JSONObject ex = fr.getJSONObject("expect");
                assertEquals(where, ex.getBoolean("fallsDetected"), r.fallsDetected);
                assertEquals(where, ex.getBoolean("fallDetected"), r.fallDetected);
                assertEquals(where, ex.isNull("fallType") ? null : ex.getString("fallType"), r.fallType);
                assertEquals(where, ex.getInt("personCount"), r.personCount);
                assertEquals(where, ints(ex.getJSONArray("personIds")), r.personIds);
                assertEquals(where, ints(ex.getJSONArray("fallenIds")), r.fallenIds);
                JSONArray ef = ex.getJSONArray("features");
                assertEquals(where, ef.length(), r.features.size());
                for (int i = 0; i < ef.length(); i++) {
                    if (ef.isNull(i)) { assertNull(where, r.features.get(i)); continue; }
                    JSONObject e = ef.getJSONObject(i);
                    for (String key : KEYS) {
                        assertEquals(where + " " + key, e.getDouble(key), value(r.features.get(i), key), EPS);
                        featureChecks++;
                    }
                }
                frames++;
                if (r.fallDetected) falls++;
            }
        }
        assertTrue("golden data must contain falls", falls > 100);
        System.out.println("fall logic golden: " + frames + " frames, " + falls + " with a fall, " + featureChecks + " feature values equal");
    }
}
