import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.ksp)
}

// Load local.properties at script top level (avoids DSL scope issues)
val localProps = Properties()
val localPropsFile = rootProject.file("local.properties")
if (localPropsFile.exists()) localProps.load(localPropsFile.inputStream())

android {
    namespace = "com.swasthya.sahayak"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.swasthya.sahayak"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        val backendUrl = localProps.getProperty("backendUrl", "http://10.0.2.2:8080")
        val speechKey = localProps.getProperty("AZURE_SPEECH_KEY", "")
        val speechRegion = localProps.getProperty("AZURE_SPEECH_REGION", "eastasia")

        buildConfigField("String", "BACKEND_URL", "\"$backendUrl\"")
        buildConfigField("String", "SPEECH_KEY", "\"$speechKey\"")
        buildConfigField("String", "SPEECH_REGION", "\"$speechRegion\"")
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
