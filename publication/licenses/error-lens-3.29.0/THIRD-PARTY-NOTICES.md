# Error Lens 3.29.0 r1 — third-party notices

This community Chinese edition is based on Error Lens by Alexander. It is not an official release from the upstream author. Product identity: `local-chinese.errorlens-zh`. Upstream version: `3.29.0`; localization revision: `1`.

Distributed VSIX SHA-256: `b5acafe76fe3953e9a03e16d0dc51351cc8a03bd627388137bd6369e7fbe0f9b`.

## Error Lens

- Copyright (c) 2023 Alexander.
- License: MIT; complete verbatim text: [Error-Lens-MIT.txt](Error-Lens-MIT.txt).
- Source: [official v3.29.0 tag](https://github.com/usernamehw/vscode-error-lens/tree/v3.29.0).
- The VSIX already includes the complete text at `extension/LICENSE.txt`, SHA-256 `6c34860f0a1fe1dcf6afcfb2f83655f6ce21a95fcd402cc118a642fccb861b1e`.
- This license covers the extension's project code, documentation and the 25 shipped upstream icon/image assets. The images match the pinned upstream tag exactly. Chinese UI translations and the separate community identity are described inside the VSIX at `extension/LOCALIZATION-NOTICE.md`.

## Lodash

- Copyright OpenJS Foundation and other contributors; based on Underscore.js, copyright Jeremy Ashkenas, DocumentCloud and Investigative Reporters & Editors.
- Version: `4.17.21`.
- License: MIT; complete verbatim text (including the upstream attribution and documentation-sample exception): [lodash-4.17.21-MIT.txt](lodash-4.17.21-MIT.txt).
- Source: [official npm version tarball](https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz), [official version license](https://github.com/lodash/lodash/blob/4.17.21/LICENSE).
- The tarball is pinned by the upstream Error Lens v3.29.0 lockfile's SHA-512 integrity and has SHA-256 `6a087ac9e5702a0c9d60fbcd48696012646ec8df1491dea472b150e79fcaf804`.
- Distributed code consists of `debounce`, `throttle` and their 13 internal Lodash helpers inside `extension/dist/extension.js`.
- The VSIX already includes the complete matching license at `extension/LICENSES/lodash-MIT.txt`, SHA-256 `f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc`. It is not dependent on this repository sidecar being downloaded.

## Distribution boundary

The 46 statically parsed bundle modules consist of 30 Error Lens project modules, 15 Lodash modules and one reference to the `vscode` API supplied by the host. VS Code itself is not distributed in this VSIX. Build-only npm tools are not installed as extension dependencies. No other JS bundle, bundled node_modules tree, WASM or native executable exists in this 37-entry VSIX.

This is a pinned-artifact attribution record, not a legal certification, trademark grant or warranty. The original licenses and upstream disclaimers govern their respective code. The full license texts travel inside the downloadable VSIX; this notice is an additional readable index.
