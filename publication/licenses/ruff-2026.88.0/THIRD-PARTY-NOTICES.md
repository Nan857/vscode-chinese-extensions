# Ruff 中文发行材料范围

- 固定官方 VSIX：Ruff 2026.88.0 / darwin-arm64；其中 CLI 为 Ruff 0.17.1。本地化未改原 Mach-O、Python、轮包许可证或 SBOM。
- JavaScript：上游固定 tag 锁定的 17 个 npm archive 完整性 SHA-512 已核对；source map 中每个第三方源码与精确 npm archive 内容逐字相同。NPM-COMPLETE-NOTICES 保留这些包实际完整许可证/版权/NOTICE，不以外层 MIT 代替。
- Rust CLI：随二进制 SBOM 的 327 个组件全部登记。292 个 registry archive 的 SHA-256 与 SBOM 及 Ruff 0.17.1 官方 Cargo.lock 同时一致。35 个内部 crate 的版本与同一官方源码 Cargo.toml 匹配；原 Ruff 根 LICENSE 20731 字节与 wheel 原文件完全相同，包含派生告知而非只有外层 MIT。
- 告知采用保守材料超集：保存 archive 中所有 LICENSE/COPYING/NOTICE/COPYRIGHT/AUTHORS 候选，不宣称每个仅构建期组件均实际进入最终 Mach-O。源归档及完整文本未做法律合规认证。
- 4 个上游仅声明 MIT、无单独许可证的 crate：collection_literals 1.0.2、quote-use 0.8.4、quote-use-macros 0.8.4、seahash 4.1.0。MIT-DECLARATIONS-AND-STANDARD-TERMS 保留原声明/已有 header，附权威 SPDX 标准 MIT 全文；该全文不是上游原文件，模板变量不填，不虚构版权人或年份。
- 完整可得源码：每个 registry crate 的稳定 HTTPS archive URL 与校验 SHA-256 见材料锁。MPL-2.0 的 version-ranges 0.1.1 未被修改，其完整 Source Code 可从 https://static.crates.io/crates/version-ranges/version-ranges-0.1.1.crate 获取；校验和及精确源 commit 见材料锁，原 MPL 全文随附。
- Rust 标准库/运行时：以原 Mach-O 内唯一 /rustc/ revision、Ruff 源 rust-toolchain 及官方发布 channel 交叉定位；不是把 Cargo SBOM 当成标准库清单。精确 revision 的原始双许可证/COPYRIGHT 及官方分发相关告知另附。
- ready（若审核后标记）仅表示本次声明范围的完整告知材料已归档，不是律师法律意见、所有系统运行通过或二进制从源码可复现证明。

标准库详细告知已取得：Rust-stdlib-1.99.0-COMPLETE-NOTICES 内保留 1,499,465 字节原 COPYRIGHT-library.html（SHA-256 5647be074c8edf7339fd863055923a8fc80bc5610a8d4661ec3b767b9d392c27），来自按官方 channel SHA 校验的 rustc 1.99.0 精确分发包；不是以外层 MIT/Apache 代替 vendor 许可。
