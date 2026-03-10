// Root build file — no code here, plugin versions declared in libs.versions.toml
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android)      apply false
    alias(libs.plugins.ksp)                 apply false
}
