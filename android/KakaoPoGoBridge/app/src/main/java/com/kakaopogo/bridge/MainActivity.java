package com.kakaopogo.bridge;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText serverUrlInput;
    private Switch enabledSwitch;
    private TextView logView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 36, 36, 36);

        TextView title = new TextView(this);
        title.setText("KakaoPoGo Bridge");
        title.setTextSize(24);
        title.setPadding(0, 0, 0, 24);
        root.addView(title);

        TextView urlLabel = new TextView(this);
        urlLabel.setText("Server URL");
        root.addView(urlLabel);

        serverUrlInput = new EditText(this);
        serverUrlInput.setSingleLine(true);
        serverUrlInput.setText(BotConfig.serverUrl(this));
        root.addView(serverUrlInput);

        Button saveButton = new Button(this);
        saveButton.setText("Save Server URL");
        saveButton.setOnClickListener(v -> {
            BotConfig.setServerUrl(this, serverUrlInput.getText().toString());
            log("Saved server URL");
            refreshLog();
        });
        root.addView(saveButton);

        enabledSwitch = new Switch(this);
        enabledSwitch.setText("Bot Enabled");
        enabledSwitch.setChecked(BotConfig.isEnabled(this));
        enabledSwitch.setOnCheckedChangeListener(this::onEnabledChanged);
        root.addView(enabledSwitch);

        Button permissionButton = new Button(this);
        permissionButton.setText("Open Notification Access Settings");
        permissionButton.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        root.addView(permissionButton);

        Button testButton = new Button(this);
        testButton.setText("Test Server");
        testButton.setOnClickListener(v -> testServer());
        root.addView(testButton);

        Button clearButton = new Button(this);
        clearButton.setText("Clear Log");
        clearButton.setOnClickListener(v -> {
            BotConfig.clearLog(this);
            refreshLog();
        });
        root.addView(clearButton);

        logView = new TextView(this);
        logView.setTextSize(13);
        logView.setPadding(0, 24, 0, 0);

        ScrollView scrollView = new ScrollView(this);
        scrollView.addView(logView);
        root.addView(scrollView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1
        ));

        setContentView(root);
        refreshLog();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshLog();
    }

    private void onEnabledChanged(CompoundButton button, boolean enabled) {
        BotConfig.setEnabled(this, enabled);
        log(enabled ? "Bot enabled" : "Bot disabled");
        refreshLog();
    }

    private void testServer() {
        BotConfig.setServerUrl(this, serverUrlInput.getText().toString());
        log("Testing server...");
        refreshLog();
        executor.execute(() -> {
            try {
                String reply = BotHttpClient.command(
                        BotConfig.serverUrl(this),
                        "/dex Pikachu",
                        "AndroidTest",
                        "Bridge"
                );
                log("Server OK: " + firstLine(reply));
            } catch (Exception e) {
                log("Server test failed: " + e.getMessage());
            }
            runOnUiThread(this::refreshLog);
        });
    }

    private String firstLine(String text) {
        int newline = text.indexOf('\n');
        return newline >= 0 ? text.substring(0, newline) : text;
    }

    private void refreshLog() {
        logView.setText(BotConfig.logs(this));
    }

    private void log(String message) {
        String stamp = new SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(new Date());
        BotConfig.appendLog(this, "[" + stamp + "] " + message);
    }
}
