# indent-rainbow 8.3.1 商店配方

固定官方字节 → plan.json 显式翻译 → deletions.json 精确删除纯开发测试文件 → 独立发行身份 → 确定性 ZIP。
原始官方包／初版五包均不改。plan.json 沿用原汉化配方，zh-cn 中文与其他语言英文回退行为不变。

- plan.json：带逐文件摘要、原文和精确次数的翻译计划。
- deletions.json：1223 个纯开发测试/构建/发布文件的逐文件 SHA-256 与字节数；没有删除运行入口或其依赖。
- dependency-proof.json：两入口 require 清单、无动态载入/文件读取的静态检查和全部省略 npm package 元数据。
- coverage.json：译文原文与上下文。
- runtime-check.cjs：桌面/Web 原始与汉化入口的 VS Code API fixture；不属于构建输入。

构建：python3 -I -B scripts/build-indent-rainbow-product.py --source OFFICIAL.vsix --output-dir NEW_DIRECTORY
双构建使用同一 CPython 3.9.6、zlib 1.2.12；不是两个 OS 或两台机器。
原生 Extension Host、真实界面及 Windows 未验证。Universal 仅表示无平台专属载荷。
