import asyncio
import hashlib
import json
import os
import zipfile

import pytest

from jarvis.backup import create_backup, preview_backup
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def selection(tmp_path):
    source = tmp_path / 'notes.md'
    source.write_text('local notes')
    return [str(source)], str(tmp_path / 'backup.zip')


def test_preview_creates_nothing_and_no_content_echo(selection):
    files, destination = selection
    result = preview_backup(files, destination)
    assert not result['created'] and not os.path.exists(destination)
    assert result['manifest']['files'][0]['sha256'] == hashlib.sha256(b'local notes').hexdigest()
    assert 'local notes' not in json.dumps(result)


def test_archive_matches_reviewed_bytes_with_manifest(selection):
    files, destination = selection
    preview = preview_backup(files, destination)
    result = create_backup(files, destination, preview['expected_manifest'])
    assert result['created']
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert archive.read('files/001.md') == b'local notes'
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['files'] == preview['manifest']['files']
    assert open(files[0]).read() == 'local notes'
    assert hashlib.sha256(open(destination, 'rb').read()).hexdigest() == result['archive_sha256']


def test_changed_file_or_destination_requires_new_review(selection, tmp_path):
    files, destination = selection
    token = preview_backup(files, destination)['expected_manifest']
    with pytest.raises(ValueError, match='changed'):
        create_backup(files, str(tmp_path / 'other.zip'), token)
    with open(files[0], 'w') as stream:
        stream.write('changed')
    with pytest.raises(ValueError, match='changed'):
        create_backup(files, destination, token)
    assert not os.path.exists(destination)


def test_no_overwrite_even_after_preview(selection):
    files, destination = selection
    token = preview_backup(files, destination)['expected_manifest']
    with open(destination, 'wb') as stream:
        stream.write(b'keep this')
    with pytest.raises(ValueError, match='already exists'):
        create_backup(files, destination, token)
    assert open(destination, 'rb').read() == b'keep this'


@pytest.mark.parametrize('name,content', [('credentials.json', '{}'), ('access-token.txt', 'value'), ('.env', 'KEY=value'),
                                       ('key.pem', 'value'), ('notes.md', '-----BEGIN PRIVATE KEY-----')])
def test_secret_heuristics_refuse_sources(tmp_path, name, content):
    source = tmp_path / name
    source.write_text(content)
    with pytest.raises(ValueError):
        preview_backup([str(source)], str(tmp_path / 'backup.zip'))


def test_duplicate_and_large_files_rejected(selection, tmp_path):
    files, destination = selection
    with pytest.raises(ValueError):
        preview_backup(files * 2, destination)
    with open(files[0], 'wb') as stream:
        stream.write(b'x' * 1_000_001)
    with pytest.raises(ValueError):
        preview_backup(files, destination)
    with pytest.raises(ValueError):
        preview_backup([], destination)
    with pytest.raises(ValueError):
        preview_backup(files * 51, destination)


def test_total_size_limit(tmp_path):
    files = []
    for i in range(11):
        source = tmp_path / f'{i}.txt'
        source.write_bytes(b'x' * 1_000_000)
        files.append(str(source))
    with pytest.raises(ValueError, match='10 MB'):
        preview_backup(files, str(tmp_path / 'backup.zip'))


def test_same_basename_files_have_unique_safe_members(tmp_path):
    files = []
    for directory in ['a', 'b']:
        root = tmp_path / directory
        root.mkdir()
        source = root / 'same.md'
        source.write_text(directory)
        files.append(str(source))
    destination = str(tmp_path / 'backup.zip')
    token = preview_backup(files, destination)['expected_manifest']
    create_backup(files, destination, token)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read('files/001.md') == b'a' and archive.read('files/002.md') == b'b'
        assert all(not n.startswith('/') and '..' not in n for n in archive.namelist())


def test_symlink_sources_and_destination_ancestors_rejected(selection, tmp_path):
    files, destination = selection
    link = tmp_path / 'link.md'
    link.symlink_to(files[0])
    with pytest.raises(ValueError, match='Symlink'):
        preview_backup([str(link)], destination)
    folder_link = tmp_path / 'folder'
    folder_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        preview_backup(files, str(folder_link / 'backup.zip'))


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='POSIX FIFO test')
def test_special_file_refused_without_blocking(tmp_path):
    path = tmp_path / 'pipe.txt'
    os.mkfifo(path)
    with pytest.raises(ValueError, match='regular'):
        preview_backup([str(path)], str(tmp_path / 'backup.zip'))


def test_registry_requires_exact_confirmation_and_stop_blocks_write(selection, tmp_path, monkeypatch):
    from jarvis.security import SecurityStore
    files, destination = selection
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'safety.db'))
    registry = build_registry(force=True)
    token = preview_backup(files, destination)['expected_manifest']
    args = dict(files=files, destination=destination, expected_manifest=token)
    assert not asyncio.run(registry.execute('create_document_backup', args, auto_approve=True)).ok
    assert not os.path.exists(destination)

    async def approve(tool, args):
        return True

    SecurityStore().set_stop(True)
    assert not asyncio.run(registry.execute('create_document_backup', args, confirm=approve)).ok
    assert not os.path.exists(destination)
    SecurityStore().set_stop(False)
    assert asyncio.run(registry.execute('create_document_backup', args, confirm=approve)).ok
