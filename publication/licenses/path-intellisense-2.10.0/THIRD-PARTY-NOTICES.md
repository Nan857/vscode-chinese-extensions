# Path Intellisense 发行许可证材料

来源为固定官方 VSIX，逐项读取包内 package.json 的精确版本，不使用根 dependencies 范围推断。完整许可文本直接按原字节保存；原许可证仍留在 VSIX。

- Path Intellisense 2.10.0 / MIT / extension/LICENSE.txt / SHA-256 4d1fba419d6b3a6ccc249f9a7ea619304e580c346b927df824f8b4b86041d625
- json5 2.2.0 / MIT / extension/node_modules/json5/LICENSE.md / SHA-256 53e59feb13058722d977c699eb0407c7bce2f93c949b681bbd2ff31698535927
- minimatch 3.0.4 / ISC / extension/node_modules/minimatch/LICENSE / SHA-256 4ec3d4c66cd87f5c8d8ad911b10f99bf27cb00cdfcff82621956e379186b016b
- brace-expansion 1.1.11 / MIT / extension/node_modules/brace-expansion/LICENSE / SHA-256 68f12f6e2c33688699249c01d8f9623c534da20aa71989c57b061b7bc1676d14
- balanced-match 1.0.2 / MIT / extension/node_modules/balanced-match/LICENSE.md / SHA-256 a1bd5deadb6a06dd74efa852c1b8b23f63b67f2214fbe9c8bd591da51da69268
- concat-map 0.0.1 / MIT / extension/node_modules/concat-map/LICENSE / SHA-256 435a6722c786b0a56fbe7387028f1d9d3f3a2d0fb615bb8fee118727c3f59b7b

这是安装包实含组件清单。原包只含离散 JavaScript 和上述 node_modules，没有额外压缩 bundle、WASM 或原生可执行文件；开发依赖和未打包依赖不作已分发组件。

原 json5/lib/cli.js 提及 minimist，但该依赖没有随原包分发；此扩展实际以 json5.parse 读取 tsconfig。未宣称其独立 CLI 可运行。
原 manifest 的 browser 入口 dist/web/extension.js 未随包分发，Web 扩展运行未验证；不修改该技术字段。
