"""Browser journal migration preserves saved metadata and transactions."""
import sqlite3
from contextlib import closing
from pathlib import Path
import pytest
from foundry.browser import BrowserStore
from foundry.storage import Store


def journal(path):
    with closing(sqlite3.connect(path)) as db:return db.execute('PRAGMA journal_mode').fetchone()[0]


def test_browser_uses_rollback_journal_and_preserves_existing_wal_workspace(tmp_path):
    home=tmp_path/'original';local=Store(home)
    saved=local.put('settings',{'id':'preferences','value':'saved before migration'})
    assert journal(local.db_path)=='wal'
    snapshots=[]
    browser=BrowserStore(home,lambda path:snapshots.append(Path(path).read_bytes()))
    assert journal(browser.db_path)=='delete'
    assert browser.get('settings','preferences')['value']==saved['value']
    with pytest.raises(ValueError):
        with browser.connect() as db:
            db.execute("UPDATE documents SET body='{}' WHERE id='preferences'")
            raise ValueError('Interrupted transaction')
    assert browser.get('settings','preferences')['value']==saved['value']
    assert snapshots
    restored=tmp_path/'restored';restored.mkdir();(restored/'workspace.sqlite3').write_bytes(snapshots[-1])
    reopened=BrowserStore(restored)
    assert journal(reopened.db_path)=='delete'
    assert reopened.get('settings','preferences')['revision']==saved['revision']
    assert reopened.get('settings','preferences')['value']==saved['value']