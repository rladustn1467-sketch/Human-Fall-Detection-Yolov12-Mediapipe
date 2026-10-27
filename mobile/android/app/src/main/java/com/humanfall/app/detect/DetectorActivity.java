package com.humanfall.app.detect;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.LocaleList;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputFilter;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.humanfall.app.BuildConfig;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Detection screen of this phone. Two ways in (DetectorPlugin):
 *  - self ('이 휴대폰으로 감지하기', the app's settings): the logged-in web app got a pairing code from the server and
 *    passes it here; this screen pairs at once, no code is shown or typed.
 *  - dedicated ('감지용 휴대전화 연결하기', below the login (first) screen, no login): the person types the code shown on
 *    their own phone (home → '기기 추가' → '감지용 휴대폰').
 * Both end up as the same kind of device on the server (type "phone": same status signal, on/off, falls, delete).
 * Then: the real state (connection, detection on/off, camera, last signal), detection on/off (same switch as in the
 * app's device list), and disconnecting this phone. Every state shown comes from the server's answers or the camera.
 */
public class DetectorActivity extends AppCompatActivity {
    public static final String EXTRA_SERVER = "server";
    public static final String EXTRA_MODE = "mode";
    public static final String EXTRA_CODE = "code";
    public static final String MODE_SELF = "self", MODE_DEDICATED = "dedicated";
    static final int REQ_CAMERA = 7;
    static final String HOW_TO_GET_CODE = "평소 쓰는 휴대폰에서 이 앱에 로그인한 뒤 홈 화면의 집에서 '기기 추가' → '감지용 휴대폰'을 고르면 6자리 연결 코드가 나와요. 그 코드를 아래에 입력해 주세요.";
    // 웹앱(server/app/next/css/main.css)과 같은 색
    static final int BG = 0xFFF4F1EA, INK = 0xFF1B2A30, PRIMARY = 0xFF1B6A72, OK = 0xFF2B8553, STOP = 0xFFC42F2A, MUTED = 0xFF5B6B70;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private DeviceLink link;
    private String server;
    private TextView stateTitle, stateBody, errorText;
    private EditText codeInput;
    private Button pairButton, toggleButton, forgetButton, permissionButton;
    private LinearLayout pairBox, pairedBox;
    private boolean busy;
    private String mode;          // self | dedicated (연결된 뒤에는 연결할 때의 방식)
    private String autoCode;      // self: 앱이 서버에서 받아 넘겨 준 연결 코드 (한 번만 씀, 화면에 보이지 않음)
    private Intent debugExtras;   // debug 빌드: 에뮬레이터 시험용 (시험용 사진 입력, 짧은 신호 간격)

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            render();
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        link = DetectorRuntime.link(this);
        server = getIntent().getStringExtra(EXTRA_SERVER);
        if (server == null) server = link.base();
        mode = link.isPaired() ? null : getIntent().getStringExtra(EXTRA_MODE);   // 연결된 뒤에는 연결할 때의 방식
        if (mode == null) mode = savedMode(this);
        autoCode = link.isPaired() ? null : getIntent().getStringExtra(EXTRA_CODE);
        if (BuildConfig.DEBUG && (getIntent().hasExtra(DetectionService.EXTRA_MOCK_FRAMES_DIR)
                || getIntent().hasExtra(DetectionService.EXTRA_HEARTBEAT_SECONDS))) {
            debugExtras = new Intent();
            debugExtras.putExtras(getIntent());
            debugExtras.removeExtra(EXTRA_SERVER);
        }
        setContentView(buildView());
        if (getSupportActionBar() != null) getSupportActionBar().hide();
        if (autoCode != null && savedInstanceState == null) pair(autoCode);
    }

    /** How this phone was connected last (self | dedicated). Dedicated when unknown. */
    static String savedMode(android.content.Context c) {
        return c.getSharedPreferences("fd_detect_ui", MODE_PRIVATE).getString("mode", MODE_DEDICATED);
    }

    private boolean self() {
        return MODE_SELF.equals(mode);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (link.isPaired()) startService();   // 앱으로 돌아오면 바로 상태 신호
        handler.post(tick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(tick);
    }

    @Override
    protected void onDestroy() {
        io.shutdown();
        super.onDestroy();
    }

    // ---- 화면 ----
    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private TextView text(int sizeSp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setLineSpacing(0, 1.2f);
        return t;
    }

    private Button button(String label, boolean primary) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(dp(14));
        bg.setColor(primary ? PRIMARY : Color.WHITE);
        if (!primary) bg.setStroke(dp(1), 0xFFD9D3C7);
        b.setBackground(bg);
        b.setTextColor(primary ? Color.WHITE : INK);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52));
        lp.topMargin = dp(10);
        b.setLayoutParams(lp);
        return b;
    }

    private View buildView() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(28), dp(20), dp(28));
        scroll.addView(root);
        // 안드로이드 15+ 는 화면 끝까지 그림: 상태 표시줄·내비게이션 막대만큼 띄움
        ViewCompat.setOnApplyWindowInsetsListener(scroll, (v, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });

        TextView title = text(24, INK, true);
        title.setText(self() ? "이 휴대폰으로 감지하기" : "감지용 휴대전화 연결하기");
        root.addView(title);
        TextView lead = text(15, MUTED, false);
        lead.setText((self() ? "평소 쓰는 이 휴대폰의 카메라로 낙상을 감지해요. 감지하는 동안에는 " : "이 휴대폰을 감지 전용으로 써요. ")
                + "휴대폰을 낙상을 볼 수 있는 곳에 세워 두고 충전기를 꽂아 두세요. 카메라 영상은 휴대폰 안에서만 낙상 판단에 쓰이고, 낙상이 감지되면 배경과 사람을 가린 사진만 가족에게 전달돼요.");
        lead.setPadding(0, dp(8), 0, dp(16));
        root.addView(lead);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(16), dp(18), dp(16));
        GradientDrawable cardBg = new GradientDrawable();
        cardBg.setCornerRadius(dp(18));
        cardBg.setColor(Color.WHITE);
        card.setBackground(cardBg);
        stateTitle = text(18, INK, true);
        stateBody = text(15, MUTED, false);
        stateBody.setPadding(0, dp(6), 0, 0);
        card.addView(stateTitle);
        card.addView(stateBody);
        root.addView(card);

        errorText = text(14, STOP, false);
        errorText.setPadding(0, dp(10), 0, 0);
        root.addView(errorText);

        pairBox = new LinearLayout(this);
        pairBox.setOrientation(LinearLayout.VERTICAL);
        pairBox.setPadding(0, dp(14), 0, 0);
        TextView label = text(14, INK, true);
        label.setText("연결 코드 (6자리)");
        pairBox.addView(label);
        codeInput = new EditText(this);
        // 연결 코드 = 영문 대문자·숫자. 한글 자판을 쓰던 휴대폰에서도 영문 키보드가 뜨도록:
        // '보이는 비밀번호' 입력 종류(키보드가 영문 자판을 띄움) + 영문 우선 힌트 + ASCII 만 입력 옵션.
        // 입력·붙여넣기한 글자는 영문·숫자만 대문자로 남김 (PairingCode.clean, "a2b 3c4" → "A2B3C4")
        codeInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        codeInput.setImeHintLocales(new LocaleList(Locale.US));
        codeInput.setImeOptions(EditorInfo.IME_ACTION_DONE | EditorInfo.IME_FLAG_FORCE_ASCII | EditorInfo.IME_FLAG_NO_EXTRACT_UI);
        codeInput.setFilters(new InputFilter[]{codeFilter(), new InputFilter.LengthFilter(8)});
        codeInput.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId != EditorInfo.IME_ACTION_DONE) return false;
            if (pairButton.isEnabled()) pair();   // 키보드의 '완료' = 연결하기
            return true;
        });
        codeInput.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        codeInput.setLetterSpacing(0.3f);
        codeInput.setGravity(Gravity.CENTER);
        codeInput.setHint("예) A2B3C4");
        codeInput.setContentDescription("연결 코드");
        pairBox.addView(codeInput);
        pairButton = button("연결하기", true);
        pairButton.setOnClickListener(v -> pair());
        pairBox.addView(pairButton);
        root.addView(pairBox);

        pairedBox = new LinearLayout(this);
        pairedBox.setOrientation(LinearLayout.VERTICAL);
        pairedBox.setPadding(0, dp(6), 0, 0);
        permissionButton = button("카메라 권한 허용하기", true);
        permissionButton.setOnClickListener(v -> askCamera());
        pairedBox.addView(permissionButton);
        toggleButton = button("", true);
        toggleButton.setOnClickListener(v -> toggle());
        pairedBox.addView(toggleButton);
        forgetButton = button("이 휴대폰에서 연결 해제", false);
        forgetButton.setOnClickListener(v -> confirmForget());
        pairedBox.addView(forgetButton);
        root.addView(pairedBox);
        return scroll;
    }

    /** Keeps only A-Z/0-9 (upper-cased) of what is typed or pasted. */
    private static InputFilter codeFilter() {
        return (source, start, end, dest, dstart, dend) -> {
            CharSequence part = source.subSequence(start, end);
            String kept = PairingCode.clean(part);
            return kept.contentEquals(part) ? null : kept;
        };
    }

    private boolean hasCamera() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private static String ago(long ms) {
        long s = Math.max(0, (System.currentTimeMillis() - ms) / 1000);
        return s < 60 ? s + "초 전" : (s / 60) + "분 전";
    }

    /** Shows only what is true now (server answers, camera frames, permission). */
    private void render() {
        boolean paired = link.isPaired();
        pairBox.setVisibility(paired ? View.GONE : View.VISIBLE);
        pairedBox.setVisibility(paired ? View.VISIBLE : View.GONE);
        pairButton.setEnabled(!busy);
        toggleButton.setEnabled(!busy);
        if (!paired) {
            // self: 코드는 앱이 넘겨 줌 (입력 칸 없음). 실패하면 설정에서 다시 시작
            pairBox.setVisibility(self() ? View.GONE : View.VISIBLE);
            String again = self() ? "앱의 설정에서 '이 휴대폰으로 감지하기'를 다시 눌러 주세요." : HOW_TO_GET_CODE;
            if (busy && self()) {
                stateTitle.setText("연결하는 중…");
                stateTitle.setTextColor(INK);
                stateBody.setText("이 휴대폰을 내 계정의 집에 연결하고 있어요.");
            } else if (link.isRevoked()) {
                stateTitle.setText("연결이 해제됐어요");
                stateTitle.setTextColor(STOP);
                stateBody.setText("앱의 기기 목록에서 이 기기가 삭제됐어요. 감지와 전송을 멈췄어요. 다시 쓰려면 " + again);
            } else {
                stateTitle.setText("아직 연결되지 않았어요");
                stateTitle.setTextColor(INK);
                stateBody.setText(server == null ? "앱의 첫 화면이나 설정에서 이 화면을 열어 주세요." : again);
            }
            pairButton.setEnabled(!busy && server != null);
            return;
        }
        DetectorRuntime.State st = DetectorRuntime.STATE;
        String place = link.location() == null ? "" : " · " + link.location();
        boolean on = link.enabled;
        String title, body;
        int color;
        if (!hasCamera()) {
            title = "카메라 권한이 필요해요";
            color = STOP;
            body = "카메라를 쓸 수 없어 낙상을 감지할 수 없어요. 아래 버튼으로 카메라 권한을 허용해 주세요.";
        } else if (!on && link.isHeld()) {
            title = "감지를 멈췄어요" + place;
            color = MUTED;
            body = "로그아웃해서 이 휴대폰의 감지를 멈췄어요. 다시 감지하려면 아래 '감지 켜기'를 눌러 주세요.";
        } else if (!on) {
            title = "감지를 꺼 두었어요" + place;
            color = MUTED;
            body = "카메라를 쓰지 않고 있어요. 감지를 켜면 다시 낙상을 감지해요.";
        } else if ("error".equals(st.camera)) {
            title = "카메라를 사용할 수 없어요" + place;
            color = STOP;
            body = "다른 앱이 카메라를 쓰고 있는지 확인한 뒤 이 화면을 다시 열어 주세요.";
        } else if (DetectorRuntime.cameraOk()) {
            title = "감지 중" + place;
            color = OK;
            body = "mock".equals(st.camera) && BuildConfig.DEBUG ? "시험용 사진으로 감지하고 있어요 (개발용 빌드)." : "카메라로 낙상을 감지하고 있어요.";
        } else {
            title = "카메라 준비 중" + place;
            color = INK;
            body = "잠시만 기다려 주세요.";
        }
        if (st.lastFallAt > 0) body += "\n마지막 낙상 감지: " + ago(st.lastFallAt);
        body += link.lastError != null ? "\n" + link.lastError + " (다시 시도 중)"
                : link.lastOkAt > 0 ? "\n서버와 연결됨 · 마지막 신호 " + ago(link.lastOkAt) : "";
        stateTitle.setText(title);
        stateTitle.setTextColor(color);
        stateBody.setText(body);
        permissionButton.setVisibility(hasCamera() ? View.GONE : View.VISIBLE);
        toggleButton.setText(on ? "감지 끄기" : "감지 켜기");
    }

    // ---- 동작 ----
    private void pair() {
        pair(codeInput.getText().toString());
    }

    private void pair(String code) {
        if (server == null) return;
        busy = true;
        errorText.setText("");
        render();
        io.execute(() -> {
            String err = link.pair(server, code);
            runOnUiThread(() -> {
                busy = false;
                if (err != null) errorText.setText(err);
                else {
                    getSharedPreferences("fd_detect_ui", MODE_PRIVATE).edit().putString("mode", mode).apply();
                    codeInput.setText("");
                    if (hasCamera()) startService();
                    else askCamera();
                }
                render();
            });
        });
    }

    private void toggle() {
        boolean turnOn = !link.enabled;
        if (turnOn && !hasCamera()) {
            askCamera();
            return;
        }
        busy = true;
        errorText.setText("");
        render();
        io.execute(() -> {
            String err = link.setEnabled(turnOn);
            runOnUiThread(() -> {
                busy = false;
                if (err != null) errorText.setText(err);
                startService();   // 서비스가 서버 값대로 카메라를 켜거나 끔
                render();
            });
        });
    }

    private void confirmForget() {
        new AlertDialog.Builder(this)
                .setTitle("이 휴대폰에서 연결을 해제할까요?")
                .setMessage("이 휴대폰은 더 이상 낙상을 감지하지 않아요. 앱의 기기 목록에서도 이 기기를 삭제해 주세요.")
                .setNegativeButton("취소", null)
                .setPositiveButton("해제", (d, w) -> {
                    DetectionService.stop(this);
                    link.forget();
                    render();
                })
                .show();
    }

    private void startService() {
        if (!DetectionService.start(this, debugExtras)) render();
    }

    private void askCamera() {
        if (!hasCamera() && !ActivityCompat.shouldShowRequestPermissionRationale(this, Manifest.permission.CAMERA)
                && getSharedPreferences("fd_detect_ui", MODE_PRIVATE).getBoolean("asked", false)) {
            // 다시 묻지 않음으로 거절한 경우: 설정 화면에서만 허용할 수 있음
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", getPackageName(), null));
            startActivity(i);
            return;
        }
        getSharedPreferences("fd_detect_ui", MODE_PRIVATE).edit().putBoolean("asked", true).apply();
        String[] perms = Build.VERSION.SDK_INT >= 33
                ? new String[]{Manifest.permission.CAMERA, Manifest.permission.POST_NOTIFICATIONS}
                : new String[]{Manifest.permission.CAMERA};
        ActivityCompat.requestPermissions(this, perms, REQ_CAMERA);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_CAMERA) return;
        if (hasCamera()) {
            errorText.setText("");
            if (link.isPaired()) startService();
        } else {
            errorText.setText("카메라 권한이 없어 감지할 수 없어요. 다시 누르면 설정 화면에서 허용할 수 있어요.");
        }
        render();
    }
}
