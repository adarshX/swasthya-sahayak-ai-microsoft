plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.ksp)
}

android {
    namespace = "com.swasthya.sahayak"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.swasthya.sahayak"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        // Set your deployed backend URL here (or override per flavor)
        buildConfigField("String", "BACKEND_URL", "\"${project.findProperty("backendUrl") ?: "http://10.0.2.2:8000"}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)

    // Room (SQLite ORM)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    // WorkManager (background sync)
    implementation(libs.androidx.work.runtime.ktx)

    // OkHttp (REST calls in SyncWorker)
    implementation(libs.okhttp)
}
