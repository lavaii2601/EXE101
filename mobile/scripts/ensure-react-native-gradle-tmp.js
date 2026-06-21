const fs = require("fs");
const path = require("path");

const reactNativeTmpDir = path.join(
  __dirname,
  "..",
  "node_modules",
  "react-native",
  "tmp"
);

if (fs.existsSync(path.dirname(reactNativeTmpDir))) {
  fs.mkdirSync(reactNativeTmpDir, { recursive: true });
}
