allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

// file_picker 8.3.7's own android/build.gradle hardcodes compileSdk 34,
// which is now too old for flutter_plugin_android_lifecycle's AAR metadata
// (it requires compileSdk >= 36) -- bumping only app/build.gradle.kts's own
// compileSdk doesn't reach this separately-generated plugin subproject, so
// force it (and any other plugin subproject with the same stale default)
// here instead. withGroovyBuilder avoids needing a compile-time dependency
// on AGP's extension classes from this root script. The evaluationDependsOn
// above can cause :app to already be evaluated by the time this runs for
// it, so this guards against Project.afterEvaluate's "already evaluated"
// error instead of assuming it always still fires in the future.
subprojects {
    if (state.executed) {
        extensions.findByName("android")?.withGroovyBuilder {
            setProperty("compileSdkVersion", 36)
        }
    } else {
        afterEvaluate {
            extensions.findByName("android")?.withGroovyBuilder {
                setProperty("compileSdkVersion", 36)
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
