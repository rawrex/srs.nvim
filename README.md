### SRS in nvim
- Scheduling is done with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).
- Currently work in progress, implemented as a Python backend with an nvim client.
- Aiming to be non-invasive. Working on making the system to be pluggable into a given knowledge base, without diffs on its current content or future content.
- Working on providing high degsee of customization, including: options config, pluggable parsers (so to say, card factories).

### Architecture
- `core/` holds the UI-agnostic backend: the index (`core/index/`), the review engine (`core/engine.py`) and the FSRS scheduler. It never reads note contents.
- The backend sends only pointers over the newline-delimited JSON protocol in `core/protocol.py`: note path, line span and card type. The nvim client (`lua/`) opens the real note and derives presentation from its contents.
- `scan.py` is an optional add-on for importing an existing vault: it scans notes, assigns card types and writes index entries. It is not part of the review flow.

### nvim plugin (in progress...)
- Requires Neovim 0.10+.
- Activate the venv that has `requirements.txt` installed
- From a buffer inside a git repository with `.srs/index.txt`, run `:SrsReview`.

### Optimizing scheduler parameters
FSRS scheduler parameters can be optimized from your accumulated review history:

```sh
python3 core/optimize.py            # optimize and save into .srs/config.json
python3 core/optimize.py --verbose  # show optimizer progress
python3 core/optimize.py --dry-run  # print optimized parameters without saving
```

- Requires the optional optimizer dependencies: `pip install "fsrs[optimizer]"` (torch, pandas, numpy, tqdm). They are lazy-loaded, so normal review/hook flows stay lightweight.
- fsrs needs at least 512 eligible (non-same-day) reviews. With less history the result equals the defaults and is **not** written.
- On success the command updates `scheduler.parameters` in `.srs/config.json`, preserving all other keys.
