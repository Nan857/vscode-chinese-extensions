#!/usr/bin/env python3
"""Rebuild the independently identified Chinese indent-rainbow from fixed upstream bytes."""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / 'localizations/indent-rainbow-8.3.1'
VERSION = '8.3.1'
SOURCE_SHA = '74e89cc9ad01dacae24dc0d2742ca1b69d0c731e5be9351a14a55bd185378d47'
UPSTREAM_ID = 'oderwat.indent-rainbow'
EXTENSION_ID = 'local-chinese.indent-rainbow-zh'
VSIX_NAME = 'indent-rainbow-zh-8.3.1.vsix'
PRODUCT_DIRECTORY = 'store-products/indent-rainbow-8.3.1'
NS = 'http://schemas.microsoft.com/developer/vsx-schema/2011'
RUNTIME = ('extension/out/src/extension.js', 'extension/dist/web/extension.js')
NOTICE = '''# indent-rainbow（中文版）

基于 oderwat.indent-rainbow 8.3.1 官方包的社区中文版本，独立发行标识为 local-chinese.indent-rainbow-zh。
VS Code 界面语言为 zh-cn 时显示中文设置说明、枚举标签和重载提示；其他界面语言保留英文回退。
保留 indentRainbow 设置键、默认值、枚举值、主入口、浏览器入口及重载命令。
与原版互斥；现有商店确认替换后安装。不会自动更新已安装版本。

官方包误带的开发测试依赖、测试代码和构建／发布辅助文件没有发运；两个运行入口都只依赖 VS Code 内置 API。
包内 DEVELOPMENT-FILES-OMITTED.json 逐文件登记省略项的原始摘要及字节数，package.json 依赖声明保持原值。
原作者 Hans Raaf 的 MIT 许可保留为 LICENSE.txt，上游 README 保留为 README.upstream.md。
本包不捆绑语言服务器或第三方运行时库。Universal 只表示没有平台专属载荷，不代表各系统运行均已验证。
验证包含包读回、同输入双构建及桌面／浏览器入口的 VS Code API fixture；原生宿主、真实界面和 Windows 未验证。
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def read_archive(raw):
    if len(raw) > 8 << 20:
        raise ValueError('source archive budget exceeded')
    result, modes, names = {}, {}, set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 16 << 20:
            raise ValueError('source expanded budget exceeded')
        for info in infos:
            name, mode = info.filename, info.external_attr >> 16
            if (not name or PurePosixPath(name).is_absolute() or '\\' in name or ':' in name or '\0' in name
                    or any(p in {'', '.', '..'} for p in name.rstrip('/').split('/'))
                    or name.casefold() in names or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or not (name.startswith('extension/') or name in {'extension.vsixmanifest', '[Content_Types].xml'})
                    or info.file_size > 8 << 20):
                raise ValueError('unsafe source entry: ' + repr(name))
            names.add(name.casefold())
            if not info.is_dir():
                result[name] = archive.read(info)
                modes[name] = mode or (stat.S_IFREG | 0o644)
    return result, modes


def package_bytes(entries, modes):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = modes.get(name, stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def technical_manifest(manifest):
    result = copy.deepcopy(manifest)
    for key in ['publisher', 'name', 'displayName', 'description', '__metadata']:
        result.pop(key, None)
    configuration = result['contributes']['configuration']
    configuration.pop('title', None)
    for value in configuration['properties'].values():
        for key in ['description', 'markdownDescription', 'enumItemLabels']:
            value.pop(key, None)
    return result


def apply_plan(entries, plan):
    originals = dict(entries)
    groups = {}
    for record in plan['replacements']:
        groups.setdefault(record['path'], []).append(record)
    for name, records in groups.items():
        raw = originals[name]
        text = raw.decode('utf8')
        edits = []
        for record in records:
            if sha(raw) != record['sha256']:
                raise ValueError('translation source mismatch: ' + name)
            positions = [m.start() for m in re.finditer(re.escape(record['before']), text)]
            if len(positions) != record['count']:
                raise ValueError('translation match count mismatch: ' + name)
            edits.extend((p, p + len(record['before']), record['after']) for p in positions)
        edits.sort()
        if any(a[1] > b[0] for a, b in zip(edits, edits[1:])):
            raise ValueError('overlapping translations')
        for start, end, replacement in reversed(edits):
            text = text[:start] + replacement + text[end:]
        entries[name] = text.encode('utf8')
    for addition in plan['additions']:
        if addition['path'] in entries:
            raise ValueError('translation addition collision')
        entries[addition['path']] = addition['content'].encode('utf8')


def build(source, output):
    if source.is_symlink() or not source.is_file():
        raise ValueError('source must be regular file')
    raw = source.read_bytes()
    if len(raw) != 3268062 or sha(raw) != SOURCE_SHA:
        raise ValueError('official source fingerprint mismatch')
    entries, modes = read_archive(raw)
    original = dict(entries)
    manifest = json.loads(entries['extension/package.json'])
    if (manifest['publisher'], manifest['name'], manifest['version']) != ('oderwat', 'indent-rainbow', VERSION):
        raise ValueError('upstream identity mismatch')
    original_manifest = copy.deepcopy(manifest)
    requires = {}
    for name in RUNTIME:
        text = entries[name].decode('utf8')
        requires[name] = re.findall(r'require\([\"\']([^\"\']+)[\"\']\)', text)
        if requires[name] != ['vscode'] or re.search(r'\b(?:import|eval)\s*\(|\brequire\s*\([^\"\']|__dirname|readFile|fetch\s*\(', text):
            raise ValueError('runtime dependency closure changed')
        if UPSTREAM_ID in text:
            raise ValueError('unreviewed hardcoded upstream runtime identity')
    deletions = json.loads((RESOURCES / 'deletions.json').read_text())
    if deletions['sourceSha256'] != SOURCE_SHA:
        raise ValueError('deletion list source mismatch')
    for record in deletions['entries']:
        name = record['path']
        if (not (name.startswith('extension/node_modules/') or name.startswith('extension/out/src/test/')
                 or name.startswith('extension/build/') or name in {'extension/test-web.sh', 'extension/publish'})
                or name in RUNTIME or sha(entries[name]) != record['sha256'] or len(entries[name]) != record['bytes']):
            raise ValueError('unapproved deletion or deletion fingerprint mismatch')
        del entries[name]
    if any('/node_modules/' in name for name in entries):
        raise ValueError('development dependency remains')
    plan = json.loads((RESOURCES / 'plan.json').read_text())
    if plan['sourceSha256'] != SOURCE_SHA:
        raise ValueError('translation plan source mismatch')
    apply_plan(entries, plan)
    manifest = json.loads(entries['extension/package.json'])
    manifest.update(publisher='local-chinese', name='indent-rainbow-zh', displayName='indent-rainbow（中文版）')
    if technical_manifest(manifest) != technical_manifest(original_manifest):
        raise ValueError('technical manifest values changed')
    entries['extension/package.json'] = json_bytes(manifest)
    english = json.loads(entries['extension/package.nls.json'])
    chinese = json.loads(entries['extension/package.nls.zh-cn.json'])
    if english.keys() != chinese.keys() or len(english) != 16:
        raise ValueError('language resource completeness mismatch')
    ET.register_namespace('', NS)
    xml = ET.fromstring(entries['extension.vsixmanifest'])
    metadata = xml.find('{' + NS + '}Metadata')
    identity = metadata.find('{' + NS + '}Identity')
    if (identity.get('Publisher'), identity.get('Id'), identity.get('Version')) != ('oderwat', 'indent-rainbow', VERSION):
        raise ValueError('upstream XML identity mismatch')
    identity.set('Publisher', 'local-chinese')
    identity.set('Id', 'indent-rainbow-zh')
    metadata.find('{' + NS + '}DisplayName').text = manifest['displayName']
    metadata.find('{' + NS + '}Description').text = chinese['localizer.description']
    entries['extension.vsixmanifest'] = ET.tostring(xml, encoding='utf-8', xml_declaration=True)
    entries['extension/README.upstream.md'] = entries['extension/README.md']
    entries['extension/README.md'] = entries['extension/LOCALIZATION-NOTICE.md'] = NOTICE.encode('utf8')
    entries['extension/DEVELOPMENT-FILES-OMITTED.json'] = json_bytes(deletions)
    localized = package_bytes(entries, modes)
    reopened, _ = read_archive(localized)
    if reopened != entries or reopened['extension/LICENSE.txt'] != original['extension/LICENSE.txt']:
        raise ValueError('base package readback or license mismatch')
    product = {'schemaVersion': 1, 'id': 'indent-rainbow', 'extensionId': EXTENSION_ID, 'upstreamId': UPSTREAM_ID,
        'name': 'indent-rainbow', 'displayName': manifest['displayName'], 'symbol': 'IR', 'version': VERSION,
        'description': chinese['localizer.description'], 'packagePath': PRODUCT_DIRECTORY + '/' + VSIX_NAME,
        'sha256': sha(localized), 'package': {'path': VSIX_NAME, 'sha256': sha(localized), 'bytes': len(localized)},
        'platforms': ['universal'], 'conflicts': [UPSTREAM_ID],
        'knownLimitations': ['zh-cn 界面显示中文，其他界面语言保留英文回退。', '原生扩展宿主、真实界面和 Windows 运行尚未验证。',
                             '官方包夹带但运行入口未引用的开发测试依赖与辅助文件未发运；依赖声明保持原值。'],
        'source': {'extensionId': UPSTREAM_ID, 'version': VERSION, 'sha256': SOURCE_SHA,
            'url': 'https://marketplace.visualstudio.com/_apis/public/gallery/publishers/oderwat/vsextensions/indent-rainbow/8.3.1/vspackage'},
        'verification': {'artifactReadback': True, 'hostActivation': False, 'windowsRuntime': False,
            'platformMeaning': 'Universal package; operating-system runtime evidence is separate.'}}
    report = {'schemaVersion': 1, 'sourceSha256': SOURCE_SHA, 'product': product, 'technicalFieldsPreserved': True,
        'licensePreserved': True, 'languageBehavior': 'zh-cn Chinese; other locales English fallback',
        'runtimeRequires': requires, 'removedFiles': len(deletions['entries']),
        'removedBytes': sum(item['bytes'] for item in deletions['entries']),
        'changedEntries': [name for name in sorted(entries) if original.get(name) != entries[name]],
        'entryHashes': {name: sha(value) for name, value in sorted(entries.items())}}
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refuse existing output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.indent-rainbow-build-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'output'
        staged.mkdir()
        (staged / VSIX_NAME).write_bytes(localized)
        (staged / 'product.json').write_bytes(json_bytes(product))
        (staged / 'verification.json').write_bytes(json_bytes(report))
        (staged / 'README.md').write_text(NOTICE)
        staged.rename(output)
    return product


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output_dir), ensure_ascii=False))
