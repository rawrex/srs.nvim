### SRS in nvim
- Scheduling is done with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).
- Currently work in progress, implemented as Python app, with TUI.
- Aiming to be non-invasive. Working on making the system to be pluggable into a given knowledge base, without diffs on its current content or future content.
- Working on providing high degsee of customization, including: options config, pluggable parsers (so to say, card factories).

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
