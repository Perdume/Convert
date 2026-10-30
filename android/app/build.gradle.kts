plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.convert.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.convert.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        // 변환 서버 주소 — 배포한 URL로 바꿔 빌드하세요:
        //   ./gradlew assembleRelease -PconverterUrl=https://내서비스.onrender.com
        val converterUrl = (project.findProperty("converterUrl") ?: "https://convert.onrender.com") as String
        buildConfigField("String", "CONVERTER_URL", "\"$converterUrl\"")
    }

    buildFeatures { buildConfig = true }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
}
