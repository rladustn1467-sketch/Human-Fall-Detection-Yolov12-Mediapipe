plugins {
    id("com.android.application")
}

android {
    namespace = "com.humanfall.falldetect"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.humanfall.falldetect"
        // MediaPipe Tasks 최소 지원 버전
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "0.1-posecheck"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // MediaPipe는 모델 파일을 압축되지 않은 상태로 읽어야 함
    androidResources {
        noCompress += listOf("task", "tflite")
    }
}

dependencies {
    implementation("com.google.mediapipe:tasks-vision:1.1.0")

    // PC에서 도는 단위 테스트 (gradlew test). Android의 org.json은 PC 테스트에서 동작하지 않아 별도 추가
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20260814")
}
