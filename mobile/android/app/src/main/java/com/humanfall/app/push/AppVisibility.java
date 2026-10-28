package com.humanfall.app.push;

/** Whether the app's main screen is on screen now (MainActivity onResume / onPause). */
public final class AppVisibility {
    private static volatile boolean onScreen;

    private AppVisibility() {
    }

    public static void set(boolean value) {
        onScreen = value;
    }

    public static boolean onScreen() {
        return onScreen;
    }
}
