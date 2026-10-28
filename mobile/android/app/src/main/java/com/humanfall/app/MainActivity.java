package com.humanfall.app;

import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;
import com.humanfall.app.detect.DetectionService;
import com.humanfall.app.detect.DetectorPlugin;
import com.humanfall.app.detect.DetectorRuntime;
import com.humanfall.app.push.AppVisibility;
import com.humanfall.app.push.PushPlugin;

public class MainActivity extends BridgeActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // 이 휴대폰의 감지 화면 (detect/): 웹앱의 설정·첫 화면이 이 플러그인으로 감지 기기 화면을 엶
        registerPlugin(DetectorPlugin.class);
        // 가족 휴대폰 푸시 알림 (push/): 알림 권한·채널, FCM 토큰, 알림을 눌러 연 사고
        registerPlugin(PushPlugin.class);
        super.onCreate(savedInstanceState);
        // 감지 기기로 연결된 폰: 앱을 켜면 감지를 이어서 함 (켜기/끄기는 서버 값대로, 카메라 권한이 있을 때만)
        if (DetectorRuntime.link(this).isPaired()) DetectionService.start(this, null);
        // 안드로이드 뒤로 가기: 웹 화면에 이전 기록이 있으면 이전 화면으로,
        // 없으면(홈 등 첫 화면) 앱을 종료하지 않고 백그라운드로 내림 (안드로이드 12 이상의 기본 동작과 같음).
        // App 플러그인의 기본 처리는 capacitor.config.ts 의 disableBackButtonHandler 로 끔 (기록이 없으면 아무 동작도 안 해서).
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView webView = bridge != null ? bridge.getWebView() : null;
                if (webView != null && webView.canGoBack()) {
                    webView.goBack();
                } else {
                    moveTaskToBack(true);
                }
            }
        });
    }

    @Override
    public void onResume() {
        super.onResume();
        AppVisibility.set(true);    // 화면에 떠 있는 동안 온 푸시는 시스템 알림으로 띄우지 않음 (앱 긴급 화면이 보여 줌)
    }

    @Override
    public void onPause() {
        super.onPause();
        AppVisibility.set(false);
        // WebView 는 쿠키를 약 30초마다 모아서 저장함. 그 전에 앱이 정리되면(최근 앱에서 밀어 닫기, 메모리 정리)
        // 방금 받은 로그인 쿠키가 사라지므로, 앱이 화면에서 내려갈 때 바로 저장
        CookieManager.getInstance().flush();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        // 최근 앱 화면을 열면 앱이 onPause 없이 그 화면에서 바로 닫힐 수 있으므로, 화면 입력을 잃을 때도 저장
        if (!hasFocus) {
            CookieManager.getInstance().flush();
        }
    }
}
