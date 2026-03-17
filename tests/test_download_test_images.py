from pathlib import Path


def test_download_specs_cover_representative_buckets():
    from scripts.download_test_images import DOWNLOAD_SPECS

    buckets = {spec.expected_bucket for spec in DOWNLOAD_SPECS}
    assert {"high_key", "normal", "low_key", "low_light_noisy", "text_ui", "faces_skin", "gradient", "high_contrast"} <= buckets
    assert len(DOWNLOAD_SPECS) >= 56

    bucket_counts = {}
    for spec in DOWNLOAD_SPECS:
        bucket_counts[spec.expected_bucket] = bucket_counts.get(spec.expected_bucket, 0) + 1
    assert bucket_counts["high_key"] >= 8
    assert bucket_counts["normal"] >= 8
    assert bucket_counts["low_key"] >= 12
    assert bucket_counts["low_light_noisy"] >= 8
    assert bucket_counts["faces_skin"] >= 6
    assert bucket_counts["text_ui"] >= 6
    assert bucket_counts["gradient"] >= 4
    assert bucket_counts["high_contrast"] >= 4


def test_download_url_builder_uses_special_filepath():
    from scripts.download_test_images import _build_download_url

    url = _build_download_url("Empty Apartment Room Window.jpg", width=1600)
    assert url.startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")
    assert "Empty%20Apartment%20Room%20Window.jpg" in url
    assert "width=1600" in url


def test_public_source_specs_include_wikimedia_commons():
    from ddic_ce.public_eval_subset import DEFAULT_PUBLIC_SOURCE_SPECS

    dataset_ids = {spec.dataset_id for spec in DEFAULT_PUBLIC_SOURCE_SPECS}
    assert "wikimedia_commons" in dataset_ids


def test_download_file_falls_back_to_curl(monkeypatch, tmp_path):
    import urllib.error

    from scripts import download_test_images as module

    destination = tmp_path / "fallback.jpg"

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("ssl eof")

    def fake_run(cmd, check, timeout):
        assert cmd[:4] == ["curl", "-sS", "-L", "--fail"]
        assert str(destination) in cmd
        destination.write_bytes(b"fallback-ok")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module._download_file("https://example.com/test.jpg", destination)
    assert destination.read_bytes() == b"fallback-ok"
