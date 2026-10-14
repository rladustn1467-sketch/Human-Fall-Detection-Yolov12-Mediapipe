package com.humanfall.falldetect.ui;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;

import com.humanfall.falldetect.PoseCheckActivity;
import com.humanfall.falldetect.R;
import com.humanfall.falldetect.events.FallReporter;
import com.humanfall.falldetect.net.ApiException;
import com.humanfall.falldetect.net.ServerConfig;

/** Start screen: shows the server settings and sends a test fall (real detection is not connected yet). */
public class MainActivity extends Activity {
    private TextView serverInfo;
    private TextView status;
    private Button sendTestFall;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        serverInfo = findViewById(R.id.server_info);
        status = findViewById(R.id.status);
        sendTestFall = findViewById(R.id.send_test_fall);

        sendTestFall.setOnClickListener(v -> sendTestFall());
        findViewById(R.id.open_settings).setOnClickListener(v ->
                startActivity(new Intent(this, SettingsActivity.class)));
        findViewById(R.id.open_pose_check).setOnClickListener(v ->
                startActivity(new Intent(this, PoseCheckActivity.class)));
    }

    @Override
    protected void onResume() {
        super.onResume();
        ServerConfig config = ServerConfig.load(this);
        // 토큰 값은 화면에 보여 주지 않음
        serverInfo.setText("서버: " + config.serverUrl
                + "\n기기 이름: " + config.deviceId
                + "\n토큰: " + (config.token.isEmpty() ? "없음 (설정 필요)" : "입력됨"));
    }

    private void sendTestFall() {
        ServerConfig config = ServerConfig.load(this);
        if (!config.isComplete()) {
            status.setText("먼저 서버 설정에서 주소와 토큰을 입력해 주세요.");
            startActivity(new Intent(this, SettingsActivity.class));
            return;
        }
        sendTestFall.setEnabled(false);
        status.setText("테스트 낙상을 서버에 보내는 중이에요... (실패하면 1·2·4초 뒤 다시 보내요)");
        FallReporter.report(this, FallReporter.TEST_FALL_TYPE, true, new FallReporter.Callback() {
            @Override
            public void onSent(String eventId) {
                if (isFinishing() || isDestroyed()) {
                    return;
                }
                sendTestFall.setEnabled(true);
                status.setText("서버가 받았어요 (기록 " + eventId.substring(0, 8) + ")");
                Intent intent = new Intent(MainActivity.this, ConfirmActivity.class);
                intent.putExtra(ConfirmActivity.EXTRA_EVENT_ID, eventId);
                startActivity(intent);
            }

            @Override
            public void onFailed(ApiException error) {
                if (isFinishing() || isDestroyed()) {
                    return;
                }
                sendTestFall.setEnabled(true);
                status.setText("보내지 못했어요: " + error.getMessage());
            }
        });
    }
}
