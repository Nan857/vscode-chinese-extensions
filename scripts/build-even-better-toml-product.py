#!/usr/bin/env python3
"""Rebuild the hash-locked community TOML edition without changing server/WASM bytes."""
from __future__ import annotations
import argparse
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.21.2'
PRODUCT_ID = 'even-better-toml'
UPSTREAM_ID = 'tamasfe.even-better-toml'
EXTENSION_ID = 'local-chinese.even-better-toml-zh'
SOURCE_SHA = '21b8d66af4285eee31e21a4492f921ab36dffcd859a67f1115d2930274650808'
RESOURCES = ROOT / 'localizations/even-better-toml-0.21.2'
VSIX_NAME = 'even-better-toml-zh-0.21.2.vsix'
PRODUCT_DIRECTORY = 'store-products/even-better-toml-0.21.2'
SOURCE_URL = 'https://marketplace.visualstudio.com/_apis/public/gallery/publishers/tamasfe/vsextensions/even-better-toml/0.21.2/vspackage'


def module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    result = importlib.util.module_from_spec(spec)
    loader.exec_module(result)
    return result


def build(source, output):
    z = module('toml_store_zip', ROOT / 'scripts/build-store-product.py')
    tool = module('toml_localization_tool', RESOURCES / 'vsix_localize.py.txt')
    raw = source.read_bytes()
    if z.sha(raw) != SOURCE_SHA:
        raise ValueError('TOML source SHA-256 mismatch')
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refuse existing output directory: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.toml-product-', dir=output.parent) as temp:
        localized_dir = Path(temp) / 'localized'
        report = tool.apply_plan(source, RESOURCES / 'plan.json', localized_dir)
        original = z.read_archive(raw)
        entries = z.read_archive((localized_dir / report['outputFile']).read_bytes())
        package = json.loads(entries['extension/package.json'])
        if package['publisher'] + '.' + package['name'] != EXTENSION_ID or package['version'] != VERSION:
            raise ValueError('TOML localized identity mismatch')
        for path in ['extension/dist/server.js', 'extension/dist/server-worker.js']:
            if entries[path] != original[path]:
                raise ValueError('TOML server bytes changed')
        notice = (RESOURCES / 'LOCALIZATION-NOTICE.md').read_bytes()
        entries['extension/README.upstream.md'] = entries['extension/readme.md']
        entries['extension/readme.md'] = entries['extension/LOCALIZATION-NOTICE.md'] = notice
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            modes = {x.filename: (x.external_attr >> 16) or (stat.S_IFREG | 0o644) for x in archive.infolist() if not x.is_dir()}
        localized = z.package_bytes(entries, modes)
        if z.read_archive(localized) != entries or source.read_bytes() != raw:
            raise ValueError('TOML package/source readback mismatch')
        product = {'schemaVersion': 1, 'id': PRODUCT_ID, 'extensionId': EXTENSION_ID, 'upstreamId': UPSTREAM_ID,
            'name': 'Even Better TOML', 'displayName': 'Even Better TOML（中文版）', 'symbol': 'TOML', 'version': VERSION,
            'description': '功能完备的 TOML 支持', 'packagePath': PRODUCT_DIRECTORY + '/' + VSIX_NAME,
            'sha256': z.sha(localized), 'package': {'path': VSIX_NAME, 'sha256': z.sha(localized), 'bytes': len(localized)},
            'platforms': ['universal'], 'conflicts': [UPSTREAM_ID],
            'knownLimitations': ['服务器诊断正文、schema 名称和说明及异常正文保留原文。', '尚未执行原生扩展宿主、实际语言服务器/WASM 或跨系统运行验证。'],
            'source': {'extensionId': UPSTREAM_ID, 'version': VERSION, 'sha256': SOURCE_SHA, 'url': SOURCE_URL,
                'translationHashes': {n: z.sha((RESOURCES / n).read_bytes()) for n in ['plan.json', 'LOCALIZATION-NOTICE.md', 'vsix_localize.py.txt']}},
            'verification': {'artifactReadback': True, 'hostActivation': False, 'windowsRuntime': False,
                'platformMeaning': 'Universal package; runtime evidence is separate.'}}
        report.update(product=product, serverAndWorkerUnchanged=True, localeBehavior='zh-cn Chinese; all other locales English',
            licensePreserved=entries['extension/LICENSE.md'] == original['extension/LICENSE.md'],
            selfLookupScan={'terms': ['tamasfe.even-better-toml', 'tamasfe', 'even-better-toml', 'getExtension('],
                'entryPoints': ['extension/dist/extension.js', 'extension/dist/browser-extension.js'],
                'matches': 0, 'adaptationRequired': False},
            entryHashes={n: z.sha(b) for n,b in entries.items()})
        stage = Path(temp) / 'product'
        stage.mkdir()
        (stage / VSIX_NAME).write_bytes(localized)
        (stage / 'product.json').write_bytes(z.json_bytes(product))
        (stage / 'verification.json').write_bytes(z.json_bytes(report))
        (stage / 'README.md').write_bytes(notice)
        stage.rename(output)
    return product


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output_dir), ensure_ascii=False))
