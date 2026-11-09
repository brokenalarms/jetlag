# Environment

## Linux cloud container

- `exiftool` and `ffmpeg` are not preinstalled: `apt-get install -y ffmpeg libimage-exiftool-perl`, then `pip install -r scripts/requirements.txt -r scripts/requirements-dev.txt` (as CI does).
- Run `pytest scripts/tests/` serially, as CI does: under `-n` (xdist) the gyroflow missing-file tests fail, and pass on their own.
- The container runs as root, which ignores `chmod 000`, so the three pipeline tests that make a source unreadable fail. Run them as an unprivileged user on a world-writable copy of the repo: `runuser -u nobody -- env HOME=/tmp python3 -m pytest -p no:cacheprovider scripts/tests/test_media_pipeline.py -k "<names>"`.
