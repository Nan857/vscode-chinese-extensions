#!/usr/bin/env python3
"""Build a Chinese Error Lens from the hash-bound official VSIX and reviewed text resources."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('store_product_zip', ROOT / 'scripts/build-store-product.py')
ZIP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ZIP)
VERSION = '3.29.0'
SOURCE_SHA = '90af40c69dad314199ff4e15b4be61ce0df9cef9d12231e99e6089b7d3a11d0f'
SOURCE_COMMIT = 'faf3756297a96ac94a96c2d28ed3efe2fbb1541b'
UPSTREAM_ID = 'usernamehw.errorlens'
EXTENSION_ID = 'local-chinese.errorlens-zh'
PRODUCT_DIRECTORY = 'store-products/error-lens-' + VERSION
VSIX_NAME = 'errorlens-zh-' + VERSION + '.vsix'
RESOURCES = ROOT / 'localizations' / ('error-lens-' + VERSION)
NOTICE = '''# Error Lens（中文版）

在代码行旁显示错误、警告及提示，并提供问题复制、排除、规则查找和状态栏信息。

基于 Error Lens 3.29.0 官方市场包制作的社区中文版，发行标识为 local-chinese.errorlens-zh。
菜单、设置说明、下拉标签、悬停按钮及插件自身提示为中文；诊断正文、用户代码与自定义模板保持原文。
本版默认中文，不添加语言切换或翻译服务。与 usernamehw.errorlens 原版互斥；商店会先确认是否替换。
保留 errorLens 设置、命令及颜色 ID，因此现有用户设置继续适用。

需要 VS Code 1.107.0 或更新版本。Mac/Windows 使用同一通用包；Windows 运行验证仍待完成。
原作者为 usernamehw。本版保留原 MIT 许可证 LICENSE.txt 和捆绑 lodash 的第三方许可。
上游说明与更新日志保留为 readme.upstream.md、changelog.md；本商店不提供插件更新功能。
'''


def pointer_parent(value, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('invalid translation pointer')
    tokens = [s.replace('~1', '/').replace('~0', '~') for s in pointer[1:].split('/')]
    parent = value
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    return parent, int(tokens[-1]) if isinstance(parent, list) else tokens[-1]


def translate_manifest(raw, resource):
    if ZIP.sha(raw) != resource['sourceSha256']:
        raise ValueError('manifest source SHA-256 mismatch')
    original = json.loads(raw)
    manifest, nls, seen = copy.deepcopy(original), {}, set()
    for index, record in enumerate(resource['translations']):
        pointer = record['pointer']
        parent, key = pointer_parent(manifest, pointer)
        if pointer in seen or parent[key] != record['before'] or not isinstance(record['after'], str):
            raise ValueError('manifest translation mismatch: ' + pointer)
        seen.add(pointer)
        nls_key = 'ui.' + str(index + 1).zfill(3)
        nls[nls_key] = record['after']
        parent[key] = '%' + nls_key + '%'
    for record in resource.get('enumLabels', []):
        parent, key = pointer_parent(manifest, record['pointer'])
        if key in parent or len(record['values']) != len(parent['enum']):
            raise ValueError('enum labels mismatch')
        parent[key] = []
        for label in record['values']:
            nls_key = 'enum.' + str(len(nls) + 1).zfill(3)
            nls[nls_key] = label
            parent[key].append('%' + nls_key + '%')
    manifest.update(publisher='local-chinese', name='errorlens-zh')
    manifest.pop('__metadata', None)
    return original, manifest, nls


def translate_runtime(raw, resource):
    if ZIP.sha(raw) != resource['sourceSha256']:
        raise ValueError('runtime source SHA-256 mismatch')
    text = raw.decode('utf8')
    edits = []
    for item in resource['replacements']:
        positions = [m.start() for m in re.finditer(re.escape(item['before']), text)]
        if len(positions) != item['count']:
            raise ValueError('runtime translation count mismatch: ' + item['before'])
        edits.extend((p, p + len(item['before']), item['after']) for p in positions)
    edits.sort()
    if any(a[1] > b[0] for a, b in zip(edits, edits[1:])):
        raise ValueError('overlapping runtime translations')
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    # These six settings links must address the independently installed edition.
    if text.count('@ext:' + UPSTREAM_ID) != 6:
        raise ValueError('runtime identity adaptation count mismatch')
    text = text.replace('@ext:' + UPSTREAM_ID, '@ext:' + EXTENSION_ID)
    return text.encode('utf8'), len(edits)


def build(source: Path, output: Path, resources: Path = RESOURCES):
    if source.is_symlink() or not source.is_file() or source.stat().st_size > ZIP.MAX_ARCHIVE:
        raise ValueError('source must be a regular bounded archive')
    data = source.read_bytes()
    if ZIP.sha(data) != SOURCE_SHA:
        raise ValueError('source SHA-256 mismatch')
    manifest_resource = json.loads((resources / 'manifest.json').read_text())
    runtime_resource = json.loads((resources / 'runtime.json').read_text())
    entries = ZIP.read_archive(data)
    originals = {name: ZIP.sha(raw) for name, raw in entries.items()}
    original, manifest, nls = translate_manifest(entries['extension/package.json'], manifest_resource)
    if (original['publisher'], original['name'], original['version']) != ('usernamehw', 'errorlens', VERSION):
        raise ValueError('upstream package identity mismatch')
    entries['extension/package.json'] = ZIP.json_bytes(manifest)
    entries['extension/package.nls.json'] = entries['extension/package.nls.zh-cn.json'] = ZIP.json_bytes(nls)
    display_name = nls[manifest['displayName'][1:-1]]
    description = nls[manifest['description'][1:-1]]
    entries['extension/dist/extension.js'], edits = translate_runtime(entries['extension/dist/extension.js'], runtime_resource)
    ET.register_namespace('', ZIP.NS)
    xml = ET.fromstring(entries['extension.vsixmanifest'])
    metadata = xml.find('{' + ZIP.NS + '}Metadata')
    identity = metadata.find('{' + ZIP.NS + '}Identity')
    if (identity.get('Publisher'), identity.get('Id'), identity.get('Version')) != ('usernamehw', 'errorlens', VERSION):
        raise ValueError('upstream XML identity mismatch')
    identity.set('Publisher', 'local-chinese')
    identity.set('Id', 'errorlens-zh')
    metadata.find('{' + ZIP.NS + '}DisplayName').text = display_name
    metadata.find('{' + ZIP.NS + '}Description').text = description
    entries['extension.vsixmanifest'] = ET.tostring(xml, encoding='utf-8', xml_declaration=True)
    entries['extension/readme.upstream.md'] = entries['extension/readme.md']
    entries['extension/readme.md'] = entries['extension/LOCALIZATION-NOTICE.md'] = NOTICE.encode('utf8')
    entries['extension/LICENSES/lodash-MIT.txt'] = (resources / 'LICENSES/lodash-MIT.txt').read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        modes = {x.filename: (x.external_attr >> 16) or (stat.S_IFREG | 0o644) for x in archive.infolist() if not x.is_dir()}
    localized = ZIP.package_bytes(entries, modes)
    reopened = ZIP.read_archive(localized)
    if reopened != entries or ZIP.sha(reopened['extension/LICENSE.txt']) != originals['extension/LICENSE.txt']:
        raise ValueError('product readback mismatch')
    packaged_xml = ET.fromstring(reopened['extension.vsixmanifest'])
    packaged_identity = packaged_xml.find('{' + ZIP.NS + '}Metadata/{' + ZIP.NS + '}Identity')
    if packaged_identity.get('Publisher') + '.' + packaged_identity.get('Id') != EXTENSION_ID:
        raise ValueError('packaged XML identity readback mismatch')
    product = {'schemaVersion': 1, 'id': 'error-lens', 'extensionId': EXTENSION_ID, 'upstreamId': UPSTREAM_ID,
               'name': 'Error Lens', 'displayName': display_name, 'symbol': 'EL', 'version': VERSION,
               'description': description,
               'packagePath': PRODUCT_DIRECTORY + '/' + VSIX_NAME, 'sha256': ZIP.sha(localized),
               'package': {'path': VSIX_NAME, 'sha256': ZIP.sha(localized), 'bytes': len(localized)},
               'platforms': ['universal'], 'conflicts': [UPSTREAM_ID],
               'knownLimitations': ['语言服务器／检查器产生的诊断正文保持原文。', 'Windows 运行验证尚未执行。'],
               'source': {'extensionId': UPSTREAM_ID, 'version': VERSION, 'sha256': SOURCE_SHA,
                          'url': 'https://marketplace.visualstudio.com/_apis/public/gallery/publishers/usernamehw/vsextensions/errorlens/' + VERSION + '/vspackage',
                          'commit': SOURCE_COMMIT,
                          'translationHashes': {name: ZIP.sha((resources / name).read_bytes()) for name in ['manifest.json', 'runtime.json', 'LICENSES/lodash-MIT.txt']}},
               'verification': {'artifactReadback': True, 'hostActivation': False, 'windowsRuntime': False,
                                'platformMeaning': 'Universal package; operating-system runtime evidence is separate.'}}
    report = {'schemaVersion': 1, 'product': product, 'manifestTranslatedStringCount': len(manifest_resource['translations']),
              'enumLabelGroups': len(manifest_resource.get('enumLabels', [])), 'runtimeTranslatedSites': edits,
              'identityAdaptedSettingsLinks': 6, 'licensePreserved': True,
              'commandsPreserved': [x['command'] for x in manifest['contributes']['commands']] == [x['command'] for x in original['contributes']['commands']],
              'changedEntries': [name for name, raw in entries.items() if originals.get(name) != ZIP.sha(raw)],
              'entryHashes': {name: ZIP.sha(raw) for name, raw in entries.items()}}
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refuse existing output directory: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.error-lens-build-', dir=output.parent) as temp:
        stage = Path(temp) / output.name
        stage.mkdir()
        (stage / VSIX_NAME).write_bytes(localized)
        (stage / 'product.json').write_bytes(ZIP.json_bytes(product))
        (stage / 'verification.json').write_bytes(ZIP.json_bytes(report))
        (stage / 'README.md').write_text(NOTICE + '\n重建：python3 scripts/build-error-lens-product.py --output-dir NEW_DIRECTORY\n')
        stage.rename(output)
    return product


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--resources', type=Path, default=RESOURCES)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output_dir, args.resources), ensure_ascii=False))
