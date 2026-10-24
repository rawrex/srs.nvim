- `index.txt` is a plain text file which contains mappings of the `card` ids to their corresponding `notes`
- It is made plain text to be transparent and simple, as we currently care only about clarity of the architecture and implementation 
- Index contains rows, each row represents an `index entry`, each `entry` provides a mapping of a `card` entity to its `note` (a container for `cards`, their context)
- Each entry contains:
  - An `id` of the index entry, which is a name of the JSON file with all the SRS data
  - The path to the note of which the card is a part of
  - Card's `type`
  - Span of lines which its `card` occupies in the `note` (start and end linenumbers)
- A cards types are predefined but may be extendable. We use card's type only to know how to represent it at each review stage
- Stages are predefined and are fixed. They constitute a state machine approach which is used to guide a review process for each card.

- We work with our SRS system by means of sessions.
- A session is a collection of due card reviews.
- At the start of each session we read all the card json files in the `.srs` dir, from which we get their due time.
  We then filter out the collected cards and leave only those which it is time to review
  The inefficient loading of all of the cards no matter their due status is a known inefficiency, for now we ignore it

- A review is a flash card review, where we ask a question which user answers and then rates the quality of the recall
- So, a review is guided by these states: question, answer, rating.
- Each card type defines how a card of that types looks at each stage.

- When we have a collection of due cards, we use their ids to find their entry in the index
- Using that entry we consturct a `Card` of a particular type, which knows its note and the location within the note

- To the nvim frontend we only care to pass the minimal data needed to correctly present the card within its note
- We open the real note file as a buffer and only change its presentation using the provided `Cards` data.
