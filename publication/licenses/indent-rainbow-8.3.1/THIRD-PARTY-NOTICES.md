# indent-rainbow 8.3.1 汉化发行告知

- 上游作者：Hans Raaf；上游扩展 ID：oderwat.indent-rainbow。
- 固定来源：官方 Marketplace 8.3.1 VSIX，完整 SHA-256 74e89cc9ad01dacae24dc0d2742ca1b69d0c731e5be9351a14a55bd185378d47。
- 本地社区发行 ID：local-chinese.indent-rainbow-zh；汉化修订：r1；本发行不是上游官方发布。
- 上游 MIT 许可全文未改，包内 extension/LICENSE.txt 与本目录 indent-rainbow-MIT.txt 相同。
- 改动：manifest 显示内容通过 NLS 支持 zh-cn、两个运行入口重载提示支持 zh-cn（其他语言仍英文）、独立发行身份、汉化说明。
- 打包清理：不发运未被运行入口引用的 node_modules 开发测试依赖、out/src/test、build 和测试／发布脚本。原包及初版汉化包保持不变。1223 个省略项的文件名、完整摘要及字节数见随包 DEVELOPMENT-FILES-OMITTED.json。
- 两个运行入口的唯一 external require 为 VS Code 自带的 vscode API；未发现动态 import、动态 require、eval、文件读取或对外 fetch。桌面入口无其余 require；Web bundle 只有 vscode 外部包装与扩展本身的缩进逻辑。本发行没有发运上述 147 个 npm 测试依赖的任何 node_modules 文件，也没有发运 APK、PrintDeps.exe 或语言服务器。
- package.json 的 dependencies/devDependencies 原声明保留，不代表本 VSIX 发运了相应代码；包内运行入口及技术配置未依赖这些测试工具。
- 验证边界：相同输入的两次构建、包读回和 mock VS Code API 下的缩进／重载分支；不声明原生宿主、真实 UI 或 Windows 运行通过。
