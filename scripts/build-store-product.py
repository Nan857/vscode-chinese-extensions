#!/usr/bin/env python3
"""Build the reviewed GitLab Chinese VSIX without launching tools or touching installations."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'a9c03d85ee23c5af1f4c526d192bdd21dab68fd1bdcc8d29b38cc0c1c1f58eed'
PATCH_SHA = '62bc7f6b1ec5d60bc98e1138290245ebe35ac1ae84ab6dd89ab7b9fe36019ddf'
EXTENSION_ID = 'local-chinese.gitlab-workflow-zh'
VERSION = '7.2.5'
DISPLAY_NAME = 'GitLab（中文版）'
DESCRIPTION = 'GitLab 7.2.5 本地中文版；使用个人访问 Token（PAT）登录。'
VSIX_NAME = 'gitlab-workflow-zh-7.2.5.vsix'
MAX_ARCHIVE, MAX_ENTRY, MAX_TOTAL, MAX_ENTRIES = 64 << 20, 64 << 20, 256 << 20, 1000
NS = 'http://schemas.microsoft.com/developer/vsx-schema/2011'
ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def projection(value) -> str:
    content = {key: item for key, item in value.items() if key != '__metadata'}
    return sha(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def read_archive(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_ARCHIVE:
        raise ValueError('archive too large')
    entries = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos, seen = archive.infolist(), set()
        if len(infos) > MAX_ENTRIES or sum(info.file_size for info in infos) > MAX_TOTAL:
            raise ValueError('archive budget exceeded')
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or '\\' in name or ':' in name or '\0' in name
                    or any(part in {'', '.', '..'} for part in name.rstrip('/').split('/'))
                    or name.casefold() in seen or stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or not (name.startswith('extension/') or name in {'extension.vsixmanifest', '[Content_Types].xml'})):
                raise ValueError('unsafe archive path: ' + repr(name))
            seen.add(name.casefold())
            if info.file_size > MAX_ENTRY:
                raise ValueError('archive entry too large')
            if not info.is_dir():
                raw = archive.read(info)
                if len(raw) != info.file_size:
                    raise ValueError('archive entry size mismatch')
                entries[name] = raw
    return entries


def apply_file(before: bytes | None, record: dict) -> bytes:
    if record['kind'] == 'create':
        if before is not None:
            raise ValueError('new file already exists')
        result = base64.b64decode(record['contentBase64'], validate=True)
    elif record['kind'] == 'modify':
        if before is None or len(before) != record['beforeBytes'] or sha(before) != record['beforeSha256']:
            raise ValueError('patch input fingerprint mismatch: ' + record['path'])
        pieces, end, last = [], 0, -1
        for edit in record['edits']:
            offset, size = edit['offsetBytes'], edit['deleteLengthBytes']
            if (type(offset) is not int or type(size) is not int or offset < end or offset <= last
                    or size < 0 or offset + size > len(before)):
                raise ValueError('invalid patch byte range')
            pieces.extend((before[end:offset], base64.b64decode(edit['insertBase64'], validate=True)))
            last, end = offset, offset + size
        pieces.append(before[end:])
        result = b''.join(pieces)
    else:
        raise ValueError('unknown patch operation')
    if len(result) != record['afterBytes'] or sha(result) != record['afterSha256']:
        raise ValueError('patch output fingerprint mismatch: ' + record['path'])
    return result


def localize_manifest(before: bytes, manifest_patch: dict) -> dict:
    result = json.loads(before)
    if manifest_patch['algorithm'] != 'manifest-projection-v1' or projection(result) != manifest_patch['beforeProjectionSha256']:
        raise ValueError('manifest input projection mismatch')
    seen = set()
    for edit in manifest_patch['edits']:
        pointer = edit['pointer']
        if pointer in seen or not pointer.startswith('/'):
            raise ValueError('duplicate or invalid manifest pointer')
        seen.add(pointer)
        tokens = [part.replace('~1', '/').replace('~0', '~') for part in pointer[1:].split('/')]
        parent = result
        for token in tokens[:-1]:
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        key = int(tokens[-1]) if isinstance(parent, list) else tokens[-1]
        if parent[key] != edit['before']:
            raise ValueError('manifest string mismatch: ' + pointer)
        parent[key] = edit['after']
    if projection(result) != manifest_patch['afterProjectionSha256']:
        raise ValueError('manifest output projection mismatch')
    return result


def text_edits(text: str, replacements: list[tuple[str, str, int]]) -> tuple[str, list[dict]]:
    """Return exact edits plus UTF-16 coordinates for the associated source map."""
    edits = []
    for old, new, count in replacements:
        positions = [m.start() for m in re.finditer(re.escape(old), text)]
        if len(positions) != count or '\n' in old or '\n' in new:
            raise ValueError('identity adaptation site mismatch: ' + old)
        for position in positions:
            prefix = text[:position]
            line = prefix.count('\n')
            column = len(prefix.rsplit('\n', 1)[-1].encode('utf-16-le')) // 2
            edits.append({'start': position, 'end': position + len(old), 'replacement': new,
                          'line': line, 'column': column, 'oldWidth': len(old.encode('utf-16-le')) // 2,
                          'newWidth': len(new.encode('utf-16-le')) // 2})
    edits.sort(key=lambda edit: edit['start'])
    if any(a['end'] > b['start'] for a, b in zip(edits, edits[1:])):
        raise ValueError('overlapping identity adaptations')
    for edit in reversed(edits):
        text = text[:edit['start']] + edit['replacement'] + text[edit['end']:]
    return text, edits


def shifted_column(line: int, column: int, edits: list[dict]) -> int:
    delta = 0
    for edit in edits:
        if edit['line'] != line or column <= edit['column']:
            continue
        width = edit['oldWidth']
        if column < edit['column'] + width:
            return edit['column'] + delta + min(column - edit['column'], edit['newWidth'])
        delta += edit['newWidth'] - width
    return column + delta


def decode_segment(segment: str) -> list[int]:
    values, value, shift = [], 0, 0
    for character in segment:
        digit = ALPHABET.index(character)
        value |= (digit & 31) << shift
        if digit & 32:
            shift += 5
        else:
            values.append(-(value >> 1) if value & 1 else value >> 1)
            value, shift = 0, 0
    if shift:
        raise ValueError('truncated source-map VLQ')
    return values


def encode_segment(values: list[int]) -> str:
    result = []
    for number in values:
        value = ((-number) << 1 | 1) if number < 0 else number << 1
        while value >= 32:
            result.append(ALPHABET[(value & 31) | 32])
            value >>= 5
        result.append(ALPHABET[value])
    return ''.join(result)


def remap_mappings(mappings: str, generated: list[dict], originals: dict[int, list[dict]]) -> str:
    source = old_line = old_column = new_column = name = 0
    lines = []
    for line_number, line in enumerate(mappings.split(';')):
        old_generated = new_generated = 0
        segments = []
        for segment in line.split(','):
            if not segment:
                continue
            fields = decode_segment(segment)
            if len(fields) not in {1, 4, 5}:
                raise ValueError('invalid source-map segment')
            old_generated += fields[0]
            current_generated = shifted_column(line_number, old_generated, generated)
            fields[0] = current_generated - new_generated
            new_generated = current_generated
            if len(fields) > 1:
                source += fields[1]
                old_line += fields[2]
                old_column += fields[3]
                current_column = shifted_column(old_line, old_column, originals.get(source, []))
                fields[3] = current_column - new_column
                new_column = current_column
                if len(fields) == 5:
                    name += fields[4]
            segments.append(encode_segment(fields))
        lines.append(','.join(segments))
    return ';'.join(lines)


def adapt_identity(entries: dict[str, bytes]) -> dict:
    js = entries['extension/extension.js'].decode('utf8')
    replacements = [('getExtension("Gitlab.gitlab-workflow")', f'getExtension("{EXTENSION_ID}")', 2),
                    ('getExtension("GitLab.gitlab-workflow")', f'getExtension("{EXTENSION_ID}")', 1),
                    ('@ext:gitlab.gitlab-workflow', f'@ext:{EXTENSION_ID}', 1),
                    ('#r=[new xlt,Szn()]', '#r=[Szn()]', 1)]
    result, generated = text_edits(js, replacements)
    source_map = json.loads(entries['extension/extension.js.map'])
    originals, sites = {}, []
    for index, (source, content) in enumerate(zip(source_map['sources'], source_map['sourcesContent'])):
        if not content:
            continue
        pairs = []
        for old in ["getExtension('Gitlab.gitlab-workflow')", "getExtension('GitLab.gitlab-workflow')"]:
            if old in content:
                pairs.append((old, f"getExtension('{EXTENSION_ID}')", content.count(old)))
        if '@ext:gitlab.gitlab-workflow' in content:
            pairs.append(('@ext:gitlab.gitlab-workflow', f'@ext:{EXTENSION_ID}', 1))
        if '#flows: Flow[] = [new OAuthFlow(), createPatFlow()]' in content:
            pairs.append(('#flows: Flow[] = [new OAuthFlow(), createPatFlow()]', '#flows: Flow[] = [createPatFlow()]', 1))
        if pairs:
            changed, edits = text_edits(content, pairs)
            source_map['sourcesContent'][index] = changed
            originals[index] = edits
            sites.append({'source': source, 'edits': len(edits)})
    if sum(len(edits) for edits in originals.values()) != 5:
        raise ValueError('source-map identity adaptation count mismatch')
    source_map['mappings'] = remap_mappings(source_map['mappings'], generated, originals)
    entries['extension/extension.js'] = result.encode()
    entries['extension/extension.js.map'] = json_bytes(source_map)
    return {'generatedEdits': len(generated), 'sourceEdits': sites, 'sourceMapCoordinatesAdjusted': True,
            'oauthFlowRemovedFromAuthenticationChoices': True, 'officialOAuthRedirectUnchangedAndUnusedByLogin': True}


def adapt_vsix_manifest(before: bytes) -> bytes:
    ET.register_namespace('', NS)
    root = ET.fromstring(before)
    metadata = root.find(f'{{{NS}}}Metadata')
    identity = metadata.find(f'{{{NS}}}Identity')
    if identity is None or identity.get('Id') != 'gitlab-workflow' or identity.get('Publisher') != 'GitLab' or identity.get('Version') != VERSION:
        raise ValueError('VSIX identity mismatch')
    identity.set('Id', 'gitlab-workflow-zh')
    identity.set('Publisher', 'local-chinese')
    metadata.find(f'{{{NS}}}DisplayName').text = DISPLAY_NAME
    metadata.find(f'{{{NS}}}Description').text = DESCRIPTION
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def package_bytes(entries: dict[str, bytes], modes: dict[str, int]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = modes.get(name, stat.S_IFREG | 0o644) << 16
            archive.writestr(info, entries[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    return stream.getvalue()


def build(source: Path, patch_path: Path, output: Path) -> dict:
    """Verify fixed inputs, transform in memory, read back, then publish one product directory."""
    if source.is_symlink() or patch_path.is_symlink():
        raise ValueError('source and patch must be regular files')
    if source.stat().st_size > MAX_ARCHIVE or patch_path.stat().st_size > 16 << 20:
        raise ValueError('input budget exceeded')
    source_bytes, patch_bytes = source.read_bytes(), patch_path.read_bytes()
    if sha(source_bytes) != SOURCE_SHA:
        raise ValueError('source SHA-256 mismatch')
    if sha(patch_bytes) != PATCH_SHA:
        raise ValueError('patch SHA-256 mismatch')
    patch = json.loads(patch_bytes)
    if patch['source']['sha256'] != SOURCE_SHA or patch['version'] != VERSION:
        raise ValueError('reviewed patch provenance mismatch')
    entries = read_archive(source_bytes)
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
        modes = {info.filename: (info.external_attr >> 16) or (stat.S_IFREG | 0o644)
                 for info in archive.infolist() if not info.is_dir()}
    original_hashes = {name: sha(content) for name, content in entries.items()}
    official = json.loads(entries['extension/package.json'])
    if (official['publisher'], official['name'], official['version']) != ('GitLab', 'gitlab-workflow', VERSION):
        raise ValueError('source package identity mismatch')
    translated = localize_manifest(entries['extension/package.json'], patch['manifest'])
    for record in patch['files']:
        name = 'extension/' + record['path']
        entries[name] = apply_file(entries.get(name), record)
    translation_hashes = {name: sha(content) for name, content in entries.items()}
    adaptation = adapt_identity(entries)
    translated.update({'publisher': 'local-chinese', 'name': 'gitlab-workflow-zh', 'displayName': DISPLAY_NAME, 'description': DESCRIPTION})
    translated['contributes']['walkthroughs'][0]['steps'][0]['description'] = (
        '本地中文版使用个人访问 Token（PAT）登录；请生成具有 api 权限的 Token。\n\n'
        '[登录 GitLab](command:gl.authenticate)。本发行不提供原官方 OAuth 登录入口。')
    entries['extension/package.json'] = json_bytes(translated)
    entries['extension.vsixmanifest'] = adapt_vsix_manifest(entries['extension.vsixmanifest'])
    notice = (
        '# GitLab 7.2.5 本地中文版\n\n'
        '本包为已审核翻译的完整 VSIX，发行身份 local-chinese.gitlab-workflow-zh，不是 GitLab 官方发布。\n\n'
        '使用个人访问 Token（PAT）登录；原官方 OAuth 登录入口在本发行中已移除。'
        '账号与服务端权限、Duo 许可和服务端返回内容仍由 GitLab 控制。未验证真实登录、OAuth 或 Windows 运行。\n\n'
        '平台事实：上游包没有 TargetPlatform，但其所带 rg 是 Linux x64 ELF。'
        'Duo 工作流的搜索能力在 Mac/Windows 上未验证且可能不可用；未为此替换上游原生依赖。\n\n'
        '本包保留官方命令、视图及设置 ID，不能与 gitlab.gitlab-workflow 同时安装使用。'
        '商店检测到官方版时应阻止安装，不自动卸载官方版。现有官方账号秘密存储不会自动迁移到新发行身份。\n\n'
        '来源：GitLab/gitlab-workflow 7.2.5；原 MIT 许可证保留在 LICENSE.txt。\n')
    entries['extension/LOCALIZATION-NOTICE.md'] = notice.encode()
    entries['extension/readme.md'] = notice.encode() + b'\n---\n\n' + entries['extension/readme.md']
    data = package_bytes(entries, modes)
    reopened = read_archive(data)
    if reopened != entries or sha(reopened['extension/LICENSE.txt']) != original_hashes['extension/LICENSE.txt']:
        raise ValueError('VSIX readback mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if any(info.external_attr >> 16 != modes.get(info.filename, stat.S_IFREG | 0o644) for info in archive.infolist()):
            raise ValueError('VSIX permissions readback mismatch')
    pkg = json.loads(reopened['extension/package.json'])
    main = pkg['main'].removeprefix('./')
    if f'extension/{main}' not in reopened and f'extension/{main}.js' not in reopened:
        raise ValueError('missing package entry point')
    identity = ET.fromstring(reopened['extension.vsixmanifest']).find(f'{{{NS}}}Metadata/{{{NS}}}Identity')
    if identity.get('Publisher') + '.' + identity.get('Id') != EXTENSION_ID or identity.get('Version') != VERSION:
        raise ValueError('packaged XML identity readback mismatch')
    changed = [name for name, content in entries.items() if original_hashes.get(name) != sha(content)]
    product = {'schemaVersion': 1, 'id': 'gitlab', 'extensionId': EXTENSION_ID,
               'upstreamId': 'gitlab.gitlab-workflow', 'name': 'GitLab', 'displayName': DISPLAY_NAME,
               'symbol': 'GL', 'version': VERSION, 'description': DESCRIPTION,
               'packagePath': f'store-products/gitlab-7.2.5/{VSIX_NAME}', 'sha256': sha(data),
               'package': {'path': VSIX_NAME, 'sha256': sha(data), 'bytes': len(data)},
               'platforms': ['universal'], 'conflicts': ['gitlab.gitlab-workflow'],
               'knownLimitations': ['本发行仅提供 PAT 登录，不提供原官方 OAuth 登录入口。',
                                    '上游通用包所带 rg 为 Linux x64 ELF；Duo 工作流搜索在 Mac/Windows 上未验证且可能不可用。'],
               'source': {'extensionId': 'gitlab.gitlab-workflow', 'version': VERSION, 'sha256': SOURCE_SHA,
                          'patchId': patch['patchId'], 'patchSha256': PATCH_SHA, 'url': patch['source']['officialVsix']},
               'verification': {'artifactReadback': True, 'hostActivation': False, 'windowsRuntime': False,
                                'liveLogin': False, 'oauth': False, 'platformMeaning': 'No VSIX TargetPlatform; runtime support is not inferred.'}}
    report = {'schemaVersion': 1, 'product': product, 'translatedFileCount': len(patch['files']),
              'manifestTranslatedStringCount': len(patch['manifest']['edits']), 'adaptation': adaptation,
              'archiveEntries': len(entries), 'uncompressedBytes': sum(map(len, entries.values())),
              'entryModes': {name: modes.get(name, stat.S_IFREG | 0o644) for name in entries},
              'main': pkg['main'], 'engines': pkg['engines'], 'licensePreserved': True,
              'commandsPreserved': [item['command'] for item in pkg['contributes']['commands']] == [item['command'] for item in official['contributes']['commands']],
              'changedEntries': changed, 'entryHashes': {name: sha(content) for name, content in entries.items()},
              'reviewedTranslationHashesBeforeIdentityAdaptation': {name: translation_hashes[name] for name in changed if name in translation_hashes}}
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refuse existing output directory: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.store-product-build-', dir=output.parent) as temp:
        stage = Path(temp) / output.name
        stage.mkdir()
        (stage / VSIX_NAME).write_bytes(data)
        (stage / 'product.json').write_bytes(json_bytes(product))
        (stage / 'verification.json').write_bytes(json_bytes(report))
        (stage / 'README.md').write_text(notice + f'\nVSIX SHA-256: `{sha(data)}`\n\n构建：`python3 scripts/build-store-product.py --output-dir PATH`。重复构建得到同一 VSIX SHA。\n', encoding='utf8')
        if sha((stage / VSIX_NAME).read_bytes()) != product['sha256']:
            raise ValueError('written VSIX readback mismatch')
        stage.rename(output)
    return product


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--patch', type=Path, default=ROOT / 'patches/gitlab-7.2.5.zh-cn.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.patch, args.output_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
