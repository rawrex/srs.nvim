### SRS in nvim
- Scheduling is done with [FSRS](https://github.com/open-spaced-repetition/py-fsrs).
- Currently work in progress, implemented as Python app, with TUI.
- Aiming to be non-invasive. Working on making the system to be pluggable into a given knowledge base, without diffs on its current content or future content.
- Working on providing high degsee of customization, including: options config, pluggable parsers (so to say, card factories).
