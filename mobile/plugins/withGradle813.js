const fs = require("fs");
const path = require("path");
const { withDangerousMod } = require("@expo/config-plugins");

module.exports = function withGradle813(config) {
  return withDangerousMod(config, [
    "android",
    async (modConfig) => {
      const wrapperPath = path.join(
        modConfig.modRequest.platformProjectRoot,
        "gradle",
        "wrapper",
        "gradle-wrapper.properties"
      );
      const wrapper = fs.readFileSync(wrapperPath, "utf8");
      const pinnedWrapper = wrapper.replace(
        /distributionUrl=https\\:\/\/services\.gradle\.org\/distributions\/gradle-[^-]+-bin\.zip/,
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.13-bin.zip"
      );

      if (wrapper === pinnedWrapper && !wrapper.includes("gradle-8.13-bin.zip")) {
        throw new Error(`Unable to pin Gradle 8.13 in ${wrapperPath}`);
      }

      fs.writeFileSync(wrapperPath, pinnedWrapper);
      return modConfig;
    },
  ]);
};
