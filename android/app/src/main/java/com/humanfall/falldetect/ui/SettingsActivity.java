package com.humanfall.falldetect.ui;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.EditText;
import android.widget.TextView;

import com.humanfall.falldetect.R;
import com.humanfall.falldetect.net.ApiException;
import com.humanfall.falldetect.net.ServerConfig;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Server address, access token and device id. The token is stored on the device only. */
public class SettingsActivity extends Activity {
    private EditText serverUrl;
    private EditText token;
    private EditText deviceId;
    private TextView result;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);
        serverUrl = findViewById(R.id.server_url);
        token = findViewById(R.id.token);
        deviceId = findViewById(R.id.device_id);
        result = findViewById(R.id.result);

        ServerConfig config = ServerConfig.load(this);
        serverUrl.setText(config.serverUrl);
        token.setText(config.token);
        deviceId.setText(config.deviceId);

        findViewById(R.id.save).setOnClickListener(v -> {
            save();
            result.setText("저장했어요.");
        });
        findViewById(R.id.check_connection).setOnClickListener(v -> checkConnection(save()));
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdownNow();
    }

    private ServerConfig save() {
        ServerConfig config = new ServerConfig(serverUrl.getText().toString(), token.getText().toString(),
                deviceId.getText().toString());
        config.save(this);
        return config;
    }

    private void checkConnection(ServerConfig config) {
        result.setText("연결을 확인하는 중이에요...");
        executor.execute(() -> {
            String message;
            try {
                config.api().checkConnection();
                message = "연결 성공: 서버 주소와 토큰이 맞아요.";
            } catch (ApiException e) {
                message = "연결 실패: " + e.getMessage();
            }
            String text = message;
            main.post(() -> {
                if (!isDestroyed()) {
                    result.setText(text);
                }
            });
        });
    }
}
