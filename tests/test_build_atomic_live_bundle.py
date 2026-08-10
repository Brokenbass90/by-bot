import hashlib
import json
import tarfile

from scripts.build_atomic_live_bundle import DEFAULT_PATHS, ROOT, build_bundle
from scripts.verify_atomic_live_bundle import verify_bundle


def test_bundle_is_committed_bounded_and_hash_verified(tmp_path):
    archive, manifest_path, manifest = build_bundle(
        repo=ROOT,
        revision="c5eba1c",
        output_dir=tmp_path / "bundle",
    )

    assert manifest["schema_id"] == "atomic_live_dependency_bundle_v1"
    assert manifest["revision"].startswith("c5eba1c")
    assert [row["path"] for row in manifest["files"]] == list(DEFAULT_PATHS)
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest

    with tarfile.open(archive, mode="r") as bundle:
        names = set(bundle.getnames())
        assert names == set(DEFAULT_PATHS) | {"bundle_manifest.json"}
        for row in manifest["files"]:
            data = bundle.extractfile(row["path"]).read()
            assert hashlib.sha256(data).hexdigest() == row["sha256"]
            assert len(data) == row["size_bytes"]

        extracted = tmp_path / "extracted"
        bundle.extractall(extracted, filter="data")

    receipt = verify_bundle(root=extracted, manifest_path=manifest_path)
    assert receipt["revision"] == manifest["revision"]
    assert receipt["verified_files"] == list(DEFAULT_PATHS)
