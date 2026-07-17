import { readFile, readdir } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url));
const violations = [];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else if ([".css", ".ts", ".tsx"].includes(extname(entry.name))) files.push(path);
  }
  return files;
}

for (const file of await walk(sourceRoot)) {
  const content = await readFile(file, "utf8");
  if (file.endsWith("theme.ts")) continue;

  if (file.endsWith(".css")) {
    const declarations = /(?:^|[;{])\s*(font-family|font-size|font-weight|line-height|color|background(?:-color)?)\s*:\s*([^;{}]+);/gim;
    for (const match of content.matchAll(declarations)) {
      const value = match[2].trim();
      const allowedKeyword = /^(inherit|currentColor)$/i.test(value);
      if (!value.includes("var(") && !allowedKeyword) {
        violations.push(`${file}: ${match[1]}: ${value}`);
      }
    }
    const withoutEmbeddedAssets = content.replace(/url\(["']?data:[\s\S]*?["']?\)/g, "");
    const directColor = /#[0-9a-f]{3,8}|rgba?\(/i.exec(withoutEmbeddedAssets);
    if (directColor) violations.push(`${file}: 样式表中存在直接颜色值 ${directColor[0]}`);
  } else {
    const directColor = /#[0-9a-f]{3,8}|rgba?\(/i.exec(content);
    if (directColor) violations.push(`${file}: 路由或组件中存在直接颜色值 ${directColor[0]}`);
  }
}

if (violations.length) {
  console.error("发现未使用设计令牌的样式：\n" + violations.join("\n"));
  process.exit(1);
}

console.log("设计令牌检查通过。");
