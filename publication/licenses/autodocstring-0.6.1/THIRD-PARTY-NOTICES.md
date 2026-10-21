# autoDocstring 发行许可证材料

来源为固定官方 VSIX，逐项读取包内 package.json 的精确版本，不使用根 dependencies 范围推断。完整许可文本直接按原字节保存；原许可证仍留在 VSIX。

- autoDocstring 0.6.1 / MIT / extension/LICENSE.txt / SHA-256 b45dabfc0ae9ace61c82135fb1814400766adc2f3415e79e7e5f7b53fc0f0d06
- @types/stack-trace 0.0.29 / MIT / extension/node_modules/@types/stack-trace/LICENSE / SHA-256 27ebda9d51f0a56b7e281ccd8230a27236dcb51c05f64b07869ecf6e965d68b0
- mustache 4.2.0 / MIT / extension/node_modules/mustache/LICENSE / SHA-256 e60b280838180a70cbb4b934f825c8119cdcf8912259ff4c6da20b284231c832
- stack-trace 0.0.10 / MIT / extension/node_modules/stack-trace/License / SHA-256 c5ece09265dbd6335030832335dec72919b9ecfd4db126cb9bb9b8d023970304
- ts-dedent 2.2.0 / MIT / extension/node_modules/ts-dedent/LICENSE / SHA-256 eff13095d9d762c3bd9dda74370c81e2130c28f2691bc455603abf973bac25b9

这是安装包实含组件清单。原包只含离散 JavaScript 和上述 node_modules，没有额外压缩 bundle、WASM 或原生可执行文件；开发依赖和未打包依赖不作已分发组件。
