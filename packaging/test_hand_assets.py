"""Optional hand assets install once, explicitly, without network access in tests."""
import base64
import hashlib
import io
import json
import tarfile
import pytest
from hub import hand_tracking as H

@pytest.fixture
def assets(monkeypatch,tmp_path):
 monkeypatch.setattr(H,'DIRECTORY',tmp_path/'models'/'hands'/H.VERSION)
 monkeypatch.setattr(H,'MODEL_SIZE',8)
 monkeypatch.setattr(H,'MODEL_SHA256',hashlib.sha256(b'model123').hexdigest())
 data=io.BytesIO()
 with tarfile.open(fileobj=data,mode='w:gz') as tar:
  for name,body in [('vision_bundle.mjs',b'export const test=1'),('wasm/vision_wasm_internal.wasm',b'wasm'),('wasm/vision_wasm_internal.js',b'loader'),('../escape',b'bad')]:
   item=tarfile.TarInfo('package/'+name);item.size=len(body);tar.addfile(item,io.BytesIO(body))
 archive=data.getvalue();monkeypatch.setattr(H,'INTEGRITY',base64.b64encode(hashlib.sha512(archive).digest()).decode())
 calls=[]
 def fetch(url,path,limit):
  calls.append(url);body=archive if url==H.ARCHIVE else b'model123';path.write_bytes(body);return len(body)
 monkeypatch.setattr(H,'_fetch',fetch)
 return calls

def test_status_never_downloads_and_install_is_cached(assets):
 assert not H.status()['ready'];assert assets==[]
 assert H.install()['ready'];assert len(assets)==2
 assert H.install()['ready'];assert len(assets)==2
 assert not (H.DIRECTORY.parent/'escape').exists()

def test_bad_runtime_integrity_is_not_served(monkeypatch,assets):
 monkeypatch.setattr(H,'INTEGRITY','wrong')
 with pytest.raises(ValueError,match='integrity'):H.install()
 assert not H.status()['ready']
 assert not (H.DIRECTORY/'manifest.json').exists()

def test_asset_names_cannot_escape_state_folder():
 for name in ['../private','wasm/../../secret','x.js','/vision_bundle.mjs','wasm/evil.html']:
  assert not H.ALLOWED.fullmatch(name)

def test_truncated_model_cannot_mark_install_ready(monkeypatch,assets):
 monkeypatch.setattr(H,'MODEL_SIZE',9)
 with pytest.raises(ValueError,match='size'):H.install()
 assert not H.status()['ready']

def test_a_model_of_the_right_size_but_the_wrong_bytes_is_refused(monkeypatch,assets):
 monkeypatch.setattr(H,'MODEL_SHA256','0'*64)
 with pytest.raises(ValueError,match='checksum'):H.install()
 assert not H.status()['ready']
