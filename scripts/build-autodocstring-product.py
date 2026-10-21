#!/usr/bin/env python3
"""Build a hash-locked, separately identified community Chinese extension; preserve locale fallback."""
from __future__ import annotations
import argparse
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / 'localizations' / 'autodocstring-0.6.1'
SPEC = importlib.util.spec_from_file_location('store_product_zip_autodocstring', ROOT / 'scripts/build-store-product.py')
ZIP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ZIP)
LOADER = SourceFileLoader('frozen_localizer_autodocstring', str(RESOURCES / 'vsix-localize.py.txt'))
TOOL_SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
TOOL = importlib.util.module_from_spec(TOOL_SPEC)
LOADER.exec_module(TOOL)


def build(source: Path, output: Path):
    config = json.loads((RESOURCES / 'config.json').read_text())
    plan = json.loads((RESOURCES / 'plan.json').read_text())
    version, product_id = config['version'], config['id']
    upstream_id = config['publisher'] + '.' + product_id
    extension_id = 'local-chinese.' + product_id + '-zh'
    asset = product_id + '-zh-' + version + '.vsix'
    raw, original_entries, original, _ = TOOL.read_source(source)
    if ZIP.sha(raw) != config['sourceSha256'] or len(raw) != config['sourceBytes']:
        raise ValueError('fixed official source fingerprint mismatch')
    if (original['publisher'], original['name'], original['version']) != (config['publisher'], product_id, version):
        raise ValueError('official extension identity mismatch')
    for locale in ['package.nls.json', 'package.nls.zh-cn.json']:
        additions = [item['content'].encode() for item in plan['additions'] if item['path'] == 'extension/' + locale]
        if additions != [(RESOURCES / locale).read_bytes()]:
            raise ValueError('translation resource and plan disagree: ' + locale)
    # Inspect exact source call sites before independent-ID adaptation: neither source uses its full ID at runtime.
    identity_hits = [name for name, (content, _, directory) in original_entries.items()
        if not directory and name.endswith('.js') and '/node_modules/' not in name and upstream_id.encode() in content]
    if identity_hits:
        raise ValueError('new source identity dependency requires explicit review')
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('refuse existing output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + product_id + '-build-', dir=output.parent) as temporary:
        temp = Path(temporary)
        plan_report = TOOL.apply_plan(source, RESOURCES / 'plan.json', temp / 'localized')
        intermediate = temp / 'localized' / plan_report['outputFile']
        _, localized_entries, localized_manifest, _ = TOOL.read_source(intermediate)
        TOOL.verify_package(original, localized_manifest, plan['target'])
        entries = {name: content for name, (content, _, directory) in localized_entries.items() if not directory}
        modes = {name: stat.S_IFREG | mode for name, (_, mode, directory) in localized_entries.items() if not directory}
        ET.register_namespace('', ZIP.NS)
        xml = ET.fromstring(entries['extension.vsixmanifest'])
        metadata = xml.find('{' + ZIP.NS + '}Metadata')
        metadata.find('{' + ZIP.NS + '}DisplayName').text = config['displayName']
        metadata.find('{' + ZIP.NS + '}Description').text = config['description']
        entries['extension.vsixmanifest'] = ET.tostring(xml, encoding='utf-8', xml_declaration=True)
        notice = ('# ' + config['displayName'] + '\n\n'
            '本包基于 ' + upstream_id + ' ' + version + ' 官方 VSIX 的固定副本制作，并非官方发行。\n'
            '发行标识：' + extension_id + '；与原扩展互斥，商店替换前会确认。\n'
            '跟随 VS Code 界面语言：zh-cn 中文，其他 locale 保留原英文回退。\n'
            '原命令 ID、配置键、默认值、枚举、用户数据及模板不变。\n'
            '原作者许可与依赖完整许可保留在原路径；另见随发行附带的许可证材料。\n'
            '上游 README 完整保留为 README.upstream.md。\n\n'
            + '\n'.join('- ' + item for item in config['knownLimitations']) + '\n')
        entries['extension/README.upstream.md'] = entries['extension/README.md']
        entries['extension/README.md'] = entries['extension/LOCALIZATION-NOTICE.md'] = notice.encode()
        localized = ZIP.package_bytes(entries, modes)
        reopened = ZIP.read_archive(localized)
        if reopened != entries:
            raise ValueError('packaged entry readback mismatch')
        for name, (content, _, directory) in original_entries.items():
            if directory:
                continue
            if name.startswith('extension/node_modules/') or name.endswith('.mustache') or name == 'extension/LICENSE.txt':
                if reopened[name] != content:
                    raise ValueError('protected dependency/template/license modified: ' + name)
        product = {'schemaVersion': 1, 'id': product_id, 'extensionId': extension_id, 'upstreamId': upstream_id,
            'name': config['name'], 'displayName': config['displayName'], 'symbol': config['symbol'], 'version': version,
            'description': config['description'], 'packagePath': 'store-products/' + product_id + '-' + version + '/' + asset,
            'sha256': ZIP.sha(localized), 'package': {'path': asset, 'sha256': ZIP.sha(localized), 'bytes': len(localized)},
            'platforms': ['universal'], 'conflicts': [upstream_id], 'knownLimitations': config['knownLimitations'],
            'source': {'extensionId': upstream_id, 'version': version, 'sha256': ZIP.sha(raw), 'url': config['sourceUrl'],
                'translationHashes': {name: ZIP.sha((RESOURCES / name).read_bytes()) for name in ['config.json', 'plan.json', 'package.nls.json', 'package.nls.zh-cn.json', 'vsix-localize.py.txt']}},
            'verification': {'artifactReadback': True, 'hostActivation': False, 'windowsRuntime': False,
                'platformMeaning': 'Universal archive; runtime and native UI evidence are separate.'}}
        report = {'schemaVersion': 1, 'product': product, 'planReport': plan_report,
            'identityRuntimeMatches': identity_hits, 'identityAdaptations': [], 'technicalManifestPreserved': True,
            'englishFallbackPreserved': reopened['extension/package.nls.json'] == (RESOURCES / 'package.nls.json').read_bytes(),
            'dependenciesAndTemplatesUnchanged': True,
            'changedEntries': sorted(name for name, content in reopened.items() if name not in original_entries or content != original_entries[name][0]),
            'entryHashes': {name: ZIP.sha(content) for name, content in reopened.items()}}
        stage = temp / 'product'
        stage.mkdir()
        (stage / asset).write_bytes(localized)
        (stage / 'product.json').write_bytes(ZIP.json_bytes(product))
        (stage / 'verification.json').write_bytes(ZIP.json_bytes(report))
        (stage / 'README.md').write_text(notice)
        if ZIP.sha(source.read_bytes()) != config['sourceSha256']:
            raise ValueError('source changed during build')
        stage.rename(output)
    return product


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output_dir), ensure_ascii=False))
