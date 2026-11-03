"""Fixture helpers only; production editors must retain their original revision."""

def fresh_master_edit(client, path, headers, changes):
    """Model opening a fresh editor for tests unrelated to stale-write behavior."""
    response = client.get(path.replace('/masters/', '/records/'), headers=headers)
    assert response.status_code == 200, response.text
    snapshot = response.json()
    version = snapshot['data']['version']
    assert type(version) is int and version >= 0, snapshot
    return {**changes, 'version': version}
