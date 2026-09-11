plugins {
    id("com.android.application")
}

android {
    namespace = "com.trooperthorn.localmdm"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.trooperthorn.localmdm"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "2026.09.11.3"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("org.nanohttpd:nanohttpd:2.3.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.json:json:20240303")
}
