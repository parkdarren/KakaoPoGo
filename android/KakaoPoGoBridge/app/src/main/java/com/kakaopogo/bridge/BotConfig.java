package com.kakaopogo.bridge;

import android.content.Context;
import android.content.SharedPreferences;

final class BotConfig {
    static final String DEFAULT_SERVER_URL = "http://YOUR_SERVER_IP:8000/command";

    private static final String PREFS = "kakaopogo_bridge";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String KEY_LOG = "log";

    private BotConfig() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static boolean isEnabled(Context context) {
        return prefs(context).getBoolean(KEY_ENABLED, false);
    }

    static void setEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    static String serverUrl(Context context) {
        String value = prefs(context).getString(KEY_SERVER_URL, DEFAULT_SERVER_URL);
        if (value == null || value.trim().isEmpty()) {
            return DEFAULT_SERVER_URL;
        }
        return value.trim();
    }

    static void setServerUrl(Context context, String serverUrl) {
        prefs(context).edit().putString(KEY_SERVER_URL, serverUrl.trim()).apply();
    }

    static String logs(Context context) {
        return prefs(context).getString(KEY_LOG, "");
    }

    static void appendLog(Context context, String line) {
        String current = logs(context);
        String next = line + "\n" + current;
        if (next.length() > 8000) {
            next = next.substring(0, 8000);
        }
        prefs(context).edit().putString(KEY_LOG, next).apply();
    }

    static void clearLog(Context context) {
        prefs(context).edit().putString(KEY_LOG, "").apply();
    }
}
