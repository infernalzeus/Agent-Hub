"""Recipes: does the same shape match, does a different one not, and does a
template stay a template?

No model is called and no app is registered — what is under test is the
signature, the promotion rule, and the refusal to reuse a port.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["HUB_TEST_IMPORT_ROOT"] = str(root)

from hub.features import ingest_recipes as IR  # noqa: E402
from hub.features import pc_control as PC  # noqa: E402


def make(tmp, name, files):
    d = Path(tmp) / name
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return d


DJANGO = {"manage.py": "# django", "requirements.txt": "django\n", "Procfile": "web: gunicorn x"}
DJANGO_WIN = {**DJANGO, "Procfile.windows": "web: python manage.py runserver %PORT%"}
FLASK = {"requirements.txt": "flask\n", "app.py": "# flask"}
NODE = {"package.json": '{"name":"x"}', "index.js": "// x"}

MANIFEST = {"cmd": ["$PYTHON", "manage.py", "runserver", "0.0.0.0:8110"], "port": 8110,
            "health_path": "/", "serve": "proxy", "install": ["$PYTHON", "-m", "pip", "install", "-r", "requirements.txt"],
            "env": {"PORT": "8110"}}


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recognises_the_framework_and_entrypoint(self):
        sig = IR.signature(make(self.tmp.name, "dj", DJANGO))
        self.assertEqual(sig["kind"], "django")
        self.assertEqual(sig["entry"], "manage.py")
        self.assertIn("Procfile", sig["procfiles"])

    def test_two_apps_of_the_same_shape_share_a_fingerprint(self):
        a = IR.signature(make(self.tmp.name, "dj1", DJANGO))
        b = IR.signature(make(self.tmp.name, "dj2", DJANGO))
        self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_a_windows_procfile_is_a_DIFFERENT_shape(self):
        """It tells you something the plain one does not, so it must not reuse
        a recipe learned without it."""
        plain = IR.signature(make(self.tmp.name, "dj3", DJANGO))
        win = IR.signature(make(self.tmp.name, "dj4", DJANGO_WIN))
        self.assertNotEqual(plain["fingerprint"], win["fingerprint"])

    def test_different_frameworks_do_not_collide(self):
        seen = {IR.signature(make(self.tmp.name, n, f))["fingerprint"]
                for n, f in (("a", DJANGO), ("b", FLASK), ("c", NODE))}
        self.assertEqual(len(seen), 3)

    def test_an_unreadable_folder_returns_nothing_rather_than_raising(self):
        self.assertEqual(IR.signature(Path(self.tmp.name) / "does-not-exist"), {})


class RecipeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = PC.DB_PATH
        PC.DB_PATH = Path(self.tmp.name) / "pc.sqlite"
        self.sig = IR.signature(make(self.tmp.name, "dj", DJANGO))

    def tearDown(self):
        PC.DB_PATH = self.old
        self.tmp.cleanup()

    def test_one_success_is_a_candidate_and_is_not_reused_yet(self):
        """A recipe used once is a guess that happened to work."""
        IR.remember(self.sig, MANIFEST)
        self.assertIsNone(IR.find(self.sig))

    def test_two_successes_promote_it_and_then_it_matches(self):
        IR.remember(self.sig, MANIFEST)
        IR.remember(self.sig, MANIFEST)
        hit = IR.find(self.sig)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["status"], "trusted")

    def test_a_failure_disables_a_candidate(self):
        IR.remember(self.sig, MANIFEST)
        IR.remember(self.sig, MANIFEST, success=False)
        self.assertIsNone(IR.find(self.sig))

    def test_a_different_shape_never_matches(self):
        IR.remember(self.sig, MANIFEST)
        IR.remember(self.sig, MANIFEST)
        other = IR.signature(make(self.tmp.name, "nd", NODE))
        self.assertIsNone(IR.find(other))

    def test_the_port_is_not_stored_in_the_recipe(self):
        """Two apps of one shape cannot both claim 8110, so the template must
        not carry a port at all."""
        IR.remember(self.sig, MANIFEST)
        with PC._db() as db:
            row = db.execute("SELECT args_json FROM pc_routines WHERE kind='ingest'").fetchone()
        self.assertNotIn("port", json.loads(row["args_json"]))

    def test_filling_a_recipe_in_picks_a_free_port(self):
        IR.remember(self.sig, MANIFEST)
        IR.remember(self.sig, MANIFEST)
        hit = IR.find(self.sig)
        man = IR.manifest_from(hit, Path(self.tmp.name), "demo", "Demo", taken={8110, 8111})
        self.assertEqual(man["port"], 8112)
        self.assertEqual(man["env"]["PORT"], "8112")
        self.assertEqual(man["cmd"], MANIFEST["cmd"])

    def test_no_free_port_means_no_manifest_rather_than_a_clash(self):
        IR.remember(self.sig, MANIFEST)
        IR.remember(self.sig, MANIFEST)
        hit = IR.find(self.sig)
        self.assertIsNone(IR.manifest_from(hit, Path(self.tmp.name), "demo", "Demo",
                                           taken=set(range(8110, 8200))))

    def test_a_manifest_with_no_command_is_not_learned(self):
        self.assertIsNone(IR.remember(self.sig, {"port": 8110}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
