package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FrameRateTest {
    @Test
    public void steadyRate() {
        FrameRate r = new FrameRate();
        assertTrue(Double.isNaN(r.fps()));
        for (int i = 0; i <= 50; i++) r.add(1000 + i * 100L, 40);   // 1초에 10장, 장당 40ms
        assertEquals(10.0, r.fps(), 1e-9);
        assertEquals(40.0, r.averageMs(), 1e-9);
    }

    @Test
    public void onlyTheLastTenSecondsCount() {
        FrameRate r = new FrameRate();
        for (int i = 0; i < 300; i++) r.add(i * 33L, 30);              // 처음 10초: 1초에 약 30장
        for (int i = 0; i <= 200; i++) r.add(10_000 + i * 100L, 90);   // 그 뒤 20초: 1초에 10장
        assertEquals(10.0, r.fps(), 1e-9);
        assertEquals(90.0, r.averageMs(), 1e-9);
    }

    @Test
    public void reportsWhenTheFirstWindowIsFullThenEveryMinute() {
        FrameRate r = new FrameRate();
        int reports = 0;
        long firstAt = -1;
        for (long t = 0; t <= 130_000; t += 100) {
            if (r.add(t, 10)) {
                reports++;
                if (firstAt < 0) firstAt = t;
            }
        }
        assertEquals(10_000, firstAt);
        assertEquals(3, reports);   // 10초, 70초, 130초
        r.clear();
        assertTrue(Double.isNaN(r.fps()));
        assertFalse(r.add(200_000, 10));
    }
}
