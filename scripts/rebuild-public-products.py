#!/usr/bin/env python3
"""Rebuild a hash-locked public product tree, using only its files and fixed official HTTPS inputs."""
from __future__ import annotations
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import runpy
import shutil
import ssl
import stat
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

MAX_SOURCE = 64 << 20
OFFICIAL_HOSTS = {'marketplace.visualstudio.com', 'gitlab.gallerycdn.vsassets.io', 'usernamehw.gallerycdn.vsassets.io'}
SOURCE_ID = 'Nan857/vscode-chinese-extensions'
RECIPE_INPUTS = {
    'gitlab': {'scripts/build-store-product.py', 'patches/gitlab-7.2.5.zh-cn.json'},
    'error-lens': {'scripts/build-store-product.py', 'scripts/build-error-lens-product.py',
        'localizations/error-lens-3.29.0/manifest.json', 'localizations/error-lens-3.29.0/runtime.json',
        'localizations/error-lens-3.29.0/LICENSES/lodash-MIT.txt'},
}



def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value or '\0' in value
            or PurePosixPath(value).is_absolute() or any(p in {'', '.', '..'} for p in value.split('/'))):
        raise ValueError('unsafe public path')
    return value


def regular(root, name, limit=4 << 20):
    path = root
    for part in relative(name).split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('public input contains symlink')
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('public input missing or exceeds budget: ' + name)
    return path.read_bytes()


def fresh_output(path):
    path = path.absolute()
    for ancestor in [path] + list(path.parents):
        if ancestor.is_symlink():
            raise ValueError('output contains symlink')
    if path.exists():
        raise ValueError('refuse existing output directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def scan_text(raw):
    text = raw.decode('utf8')
    if re.search(r'(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:/Users/|/home/)[A-Za-z0-9_.-]+/|[A-Z]:\\\\Users\\\\)', text):
        raise ValueError('public text contains credential or local home path')


def validate_repository(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('repository must be regular directory')
    root = root.resolve()
    lock = parse_json(regular(root, 'source-lock.json'))
    if lock.get('schemaVersion') != 1 or lock.get('sourceId') != SOURCE_ID:
        raise ValueError('unsupported public source lock')
    files = lock.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('public source whitelist is missing')
    actual = set()
    for directory, directories, names in os.walk(root, followlinks=False):
        directory = Path(directory)
        for name in directories + names:
            path = directory / name
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise ValueError('public tree contains nonregular input')
        if directory == root:
            # VCS metadata is not source input: never traverse or read its contents.
            directories[:] = [name for name in directories if name != '.git']
        for name in names:
            if directory == root and name == '.git':
                continue
            actual.add((directory / name).relative_to(root).as_posix())
    permitted = set(files) | {'source-lock.json'}
    if actual not in (permitted, permitted | {'catalog.json'}):
        raise ValueError('unexpected public file')
    for name, expected in files.items():
        raw = regular(root, name)
        if len(raw) != expected['bytes'] or sha(raw) != expected['sha256']:
            raise ValueError('public input fingerprint mismatch: ' + name)
        scan_text(raw)
    products = lock.get('products')
    if not isinstance(products, list) or not products or len(products) > 2:
        raise ValueError('invalid public products')
    ids = set()
    allowed_files = {'README.md', 'scripts/rebuild-public-products.py', 'scripts/product-release-check.py', 'publication/license-manifest.json'}
    for product in products:
        product_id = product['id']
        if product_id not in {'gitlab', 'error-lens'} or product_id in ids:
            raise ValueError('invalid or duplicate product')
        ids.add(product_id)
        expected_inputs = RECIPE_INPUTS[product_id]
        paths = [item['path'] for item in product['recipe']['inputs']]
        if len(paths) != len(set(paths)) or set(paths) != expected_inputs:
            raise ValueError('unapproved recipe inputs')
        expected_script = 'scripts/build-store-product.py' if product_id == 'gitlab' else 'scripts/build-error-lens-product.py'
        if product['recipe']['script'] != expected_script:
            raise ValueError('unapproved recipe script')
        allowed_files.update(paths)
        allowed_files.add('products/' + product_id + '.json')
        for file in product['licenseFiles']:
            relative(file)
            if not file.startswith(('publication/licenses/', 'publication/notices/')):
                raise ValueError('unapproved license export path')
            allowed_files.add(file)
        metadata = parse_json(regular(root, 'products/' + product_id + '.json'))
        if any(metadata[key] != product[key] for key in ('id', 'extensionId', 'upstreamId', 'version')) or metadata['artifacts'] != [product['artifact']]:
            raise ValueError('public product metadata mismatch')
        url_check(product['upstream']['url'])
        for item in product['recipe']['inputs']:
            if files.get(item['path']) != {k: item[k] for k in ('sha256', 'bytes')}:
                raise ValueError('recipe differs from public whitelist')
        artifact = product['artifact']
        if artifact['url'] != 'https://github.com/' + SOURCE_ID + '/releases/download/' + artifact['tag'] + '/' + artifact['assetName']:
            raise ValueError('artifact is not fixed source')
        for name in [artifact['tag'], artifact['assetName'], product['base']['assetName']]:
            if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,150}', name):
                raise ValueError('unsafe release name')
    if set(files) != allowed_files:
        raise ValueError('unexpected public whitelist file')
    licenses = parse_json(regular(root, 'publication/license-manifest.json'))
    if licenses.get('schemaVersion') != 1 or set(licenses.get('products', {})) != ids:
        raise ValueError('public license manifest product mismatch')
    for product in products:
        license_product = licenses['products'][product['id']]
        component_files = {file for component in license_product['components'] for file in component['files']}
        if (license_product.get('status') != 'ready' or license_product.get('unresolved') != []
                or license_product.get('requiredRevision') != product['artifact']['localizationRevision']
                or component_files != set(product['licenseFiles'])):
            raise ValueError('publication blocked: ' + product['id'])
    if 'catalog.json' in actual:
        validate_published_catalog(root, lock)
    return root, lock


def validate_published_catalog(root, lock):
    catalog = parse_json(regular(root, 'catalog.json', 1 << 20))
    fields = {'schemaVersion', 'sourceId', 'revision', 'issuedAt', 'minManagerVersion', 'products'}
    if (not isinstance(catalog, dict) or set(catalog) != fields
            or type(catalog.get('schemaVersion')) is not int or catalog['schemaVersion'] != 1
            or catalog.get('sourceId') != SOURCE_ID.lower()
            or type(catalog.get('revision')) is not int or not 1 <= catalog['revision'] < 2 ** 53
            or not isinstance(catalog.get('minManagerVersion'), str)
            or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', catalog['minManagerVersion'])):
        raise ValueError('invalid published catalog envelope')
    try:
        timestamp = catalog['issuedAt']
        if not isinstance(timestamp, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', timestamp):
            raise ValueError('timestamp')
        datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise ValueError('invalid published catalog timestamp') from None
    expected_products = []
    for locked in lock['products']:
        metadata = parse_json(regular(root, 'products/' + locked['id'] + '.json'))
        product = {key: metadata[key] for key in ('id', 'extensionId', 'upstreamId', 'name', 'description',
            'symbol', 'version', 'localizationRevision', 'knownLimitations')}
        product['artifacts'] = [{key: artifact[key] for key in ('targetPlatform', 'enginesVscode', 'url',
            'bytes', 'sha256', 'verificationProfile')} for artifact in metadata['artifacts']]
        expected_products.append(product)
    if json.dumps(catalog['products'], sort_keys=True) != json.dumps(expected_products, sort_keys=True):
        raise ValueError('published catalog differs from locked product release')


def url_check(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in OFFICIAL_HOSTS or parts.username or parts.password
            or parts.port not in (None, 443) or parts.fragment or parts.query or '%' in parts.path
            or '..' in parts.path.split('/')):
        raise ValueError('unapproved official download origin')
    if parts.hostname == 'marketplace.visualstudio.com':
        if not re.fullmatch(r'/_apis/public/gallery/publishers/usernamehw/vsextensions/errorlens/3\.29\.0/vspackage', parts.path):
            raise ValueError('unapproved official marketplace path')
    elif not re.fullmatch(r'/extensions/(?:gitlab/gitlab-workflow/7\.2\.5|usernamehw/errorlens/3\.29\.0)/[0-9]+/Microsoft\.VisualStudio\.Services\.VSIXPackage', parts.path):
        raise ValueError('unapproved official CDN path')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, request, fp, code, message, headers, newurl):
        self.count += 1
        if self.count > 3:
            raise ValueError('official download redirect budget exceeded')
        url_check(newurl)
        return urllib.request.Request(newurl, headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Chinese-Extensions-Public-Rebuild/1'})


def download(source, destination):
    url_check(source['url'])
    opener = urllib.request.build_opener(SafeRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    started = time.monotonic()
    request = urllib.request.Request(source['url'], headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Chinese-Extensions-Public-Rebuild/1'})
    with opener.open(request, timeout=20) as response:
        encoding = response.headers.get('Content-Encoding', 'identity').lower()
        if encoding not in {'gzip', 'identity'}:
            raise ValueError('unsupported official HTTP content encoding')
        content = bytearray()
        while True:
            if time.monotonic() - started > 180:
                raise ValueError('official download total budget exceeded')
            block = response.read(64 << 10)
            if not block:
                break
            content.extend(block)
            if len(content) > MAX_SOURCE:
                raise ValueError('official download exceeds budget')
    if encoding == 'gzip':
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(content, MAX_SOURCE + 1)
        if len(raw) > MAX_SOURCE or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('official gzip exceeds budget or is incomplete')
    else:
        raw = bytes(content)
    if len(raw) != source['bytes'] or sha(raw) != source['sha256'] or not raw.startswith(b'PK\x03\x04'):
        raise ValueError('official VSIX fingerprint mismatch')
    destination.write_bytes(raw)
    return {'bytes': len(raw), 'sha256': sha(raw), 'contentEncoding': encoding}


def revision_package(root, product, base):
    revision = product['artifact']['localizationRevision']
    if revision == 1:
        return base
    if revision != 2:
        raise ValueError('unreviewed localization revision')
    spec = importlib.util.spec_from_file_location('public_product_zip', root / 'scripts/build-store-product.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    entries = helper.read_archive(base)
    modes = {}
    with zipfile.ZipFile(io.BytesIO(base)) as archive:
        modes = {item.filename: item.external_attr >> 16 for item in archive.infolist()}
    original = dict(entries)
    for file in product['licenseFiles']:
        name = 'extension/LICENSES/' + file
        raw = regular(root, file)
        if name in entries and entries[name] != raw:
            raise ValueError('license wrapper entry conflict')
        entries[name] = raw
    marker = 'extension/LOCALIZATION-METADATA.json'
    if marker in entries:
        raise ValueError('base already contains localization metadata')
    entries[marker] = json_bytes({'schemaVersion': 1, 'productId': product['id'], 'extensionId': product['extensionId'],
        'upstreamId': product['upstreamId'], 'upstreamVersion': product['version'],
        'upstreamSha256': product['upstream']['sha256'], 'localizationRevision': revision})
    result = helper.package_bytes(entries, modes)
    reopened = helper.read_archive(result)
    if any(reopened[name] != raw for name, raw in original.items()):
        raise ValueError('license wrapper changed original payload')
    return result



def execute_recipe(script, args, cwd, environment):
    """Run one reviewed pure-Python recipe in fresh globals, not a child process."""
    previous_cwd, previous_argv = Path.cwd(), sys.argv
    previous_path, path_values = sys.path, list(sys.path)
    previous_environment, environment_values = os.environ, dict(os.environ)
    stdout, stderr = io.StringIO(), io.StringIO()
    status = 0
    try:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(environment)
        sys.argv = [str(script)] + list(args)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script), run_name='__main__')
            except SystemExit as error:
                if error.code is None:
                    status = 0
                elif isinstance(error.code, int):
                    status = int(error.code)
                else:
                    print(error.code, file=sys.stderr)
                    status = 1
            except Exception:
                traceback.print_exc()
                status = 1
    finally:
        sys.argv = previous_argv
        sys.path = previous_path
        sys.path[:] = path_values
        os.environ = previous_environment
        os.environ.clear()
        os.environ.update(environment_values)
        os.chdir(previous_cwd)
    return {'exitStatus': status, 'stdout': stdout.getvalue(), 'stderr': stderr.getvalue(), 'executionMode': 'runpy-context'}


def run_builds(root, lock, output):
    runtime = lock['runtime']
    observed = {'implementation': platform.python_implementation(), 'python': platform.python_version(), 'zlib': zlib.ZLIB_RUNTIME_VERSION}
    if observed != runtime:
        raise ValueError('reproducible build runtime differs from source lock: ' + json.dumps(observed))
    output = fresh_output(output)
    records = []
    with tempfile.TemporaryDirectory(prefix='.public-rebuild-', dir=output.parent) as temporary:
        work = Path(temporary)
        # Recipe paths refer only to the exact public tree and newly downloaded inputs.
        clean = work / 'repository'
        clean.mkdir()
        for name in sorted(set(lock['files']) | {'source-lock.json'}):
            raw = regular(root, name)
            if name == 'source-lock.json':
                if parse_json(raw) != lock:
                    raise ValueError('public source lock changed before build')
            elif {'sha256': sha(raw), 'bytes': len(raw)} != lock['files'][name]:
                raise ValueError('public input changed before build: ' + name)
            target = clean / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        validate_repository(clean)
        home = work / 'home'
        home.mkdir()
        sources = work / 'sources'
        sources.mkdir()
        release = work / 'releases'
        release.mkdir()
        environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(home), 'TMPDIR': str(work), 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        for product in lock['products']:
            source = sources / (product['id'] + '.vsix')
            record = {'id': product['id'], 'official': download(product['upstream'], source), 'builds': []}
            previous = None
            for repeat in (1, 2):
                build = work / (product['id'] + '-' + str(repeat))
                args = ['--source', str(source), '--output-dir', str(build)]
                result = execute_recipe(clean / product['recipe']['script'], args, clean, environment)
                if result['exitStatus']:
                    raise ValueError('public builder failed: ' + product['id'] + ': ' + result['stderr'][:500])
                base = regular(build, product['base']['assetName'], MAX_SOURCE)
                if sha(base) != product['base']['sha256'] or len(base) != product['base']['bytes']:
                    raise ValueError('base rebuild fingerprint mismatch: ' + product['id'])
                data = revision_package(clean, product, base)
                expected = product['artifact']
                if sha(data) != expected['sha256'] or len(data) != expected['bytes'] or (previous is not None and data != previous):
                    raise ValueError('final rebuild fingerprint mismatch: ' + product['id'])
                previous = data
                record['builds'].append({'repeat': repeat, **result, 'sha256': sha(data), 'bytes': len(data)})
            target = release / product['artifact']['tag']
            target.mkdir()
            (target / product['artifact']['assetName']).write_bytes(previous)
            records.append(record)
        staged = work / 'output'
        staged.mkdir()
        shutil.move(str(release), staged / 'releases')
        report = {'schemaVersion': 1, 'status': 'PASS_TWO_REBUILDS', 'sourceLockSha256': sha(regular(clean, 'source-lock.json')),
            'runtime': observed, 'buildExecution': 'Two fresh runpy contexts in one isolated Python interpreter; no child process.',
            'inputFiles': lock['files'], 'products': records, 'publicationExecuted': False}
        (staged / 'product-release-report.json').write_bytes(json_bytes(report))
        staged.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--validate-only', action='store_true', help='Verify the exact public tree without network or build claims.')
    args = parser.parse_args()
    root, lock = validate_repository(args.repository)
    if args.validate_only:
        result = {'status': 'PASS_PUBLIC_INPUTS_ONLY', 'products': [p['id'] for p in lock['products']], 'networkRequests': 0, 'builds': 0}
    else:
        if not args.output:
            parser.error('--output is required for rebuilds')
        result = run_builds(root, lock, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
