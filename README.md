### SRS in nvim
- Scheduling is done with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).
- Aiming to be non-invasive, to be pluggable into an existing vault, without diffs on its current content.

### Architecture
- `core/` holds the Python backend: the index (`core/index/`), the review engine (`core/engine.py`) and the FSRS scheduler. Index is used to map SRS cards to their source note locations, in a plain text to aid transparency and ease seeing what is going on.
- The backend is driven by the nvim client over the newline-delimited JSON protocol in `core/protocol.py`.
- `scripts/scan.py` is an optional add-on for SRSing an existing vault (or a part of it). Current syntax supports only markdown asterisk-based emphasis as text clozes and callouts as QA format of cards. One line containing emphasis becomes one card.

### Nvim
- Requires Neovim 0.10+.
- Activate the venv that has `requirements.txt` installed
- From a buffer inside a git repository with `.srs/index.txt`, run `:SrsReview`.
