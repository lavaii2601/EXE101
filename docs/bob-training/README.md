# Bob training documents

Bob does not fine-tune a base model in this repo. These files are imported into
the FlowMate knowledge base through `scripts/train_bob.py` and used as RAG
context during chat.

In addition, `services/bob_training_cases.py` generates exactly 500 labelled
phrases for every executable tool intent (currently 12 intents / 6,000 cases).
Unlike the passive RAG documents, this corpus trains Bob's built-in offline
classifier and is also imported in compact 50-case batches during deployment.
The 500 phrases per intent are deterministic combinations of reviewed semantic
cores, prefixes, and suffixes; they should not be interpreted as 500 unrelated
human conversations. The cores now include Vietnamese, English, and real
code-switch forms for every tool family.

Language/context behavior is not left to RAG retrieval alone. Runtime code also:

- detects explicit Vietnamese, English, or bilingual output requests;
- understands code-switch prompts as one goal with shared entities/constraints;
- lets neutral turns such as `OK` inherit the last clear session language;
- injects recent same-session dialogue even when email/calendar/web workspace
  evidence is present;
- resolves elliptical follow-ups through the AI intent contextualizer without
  caching phrases such as `do it` outside their original session;
- keeps the newest correction, negation, and constraint above older history.
- filters mode-tagged RAG candidates to the active mode while retaining shared
  safety rules and the user's own learned knowledge.

## Files by mode

All RAG rules now live under `modes/` using schema version 2. The previous six
topic files were consolidated so deploy and manual training read one complete,
predictable corpus:

- `shared.json`: behavior shared by every mode, including intent, safety,
  privacy, web research, auth, email and calendar fundamentals.
- `student.json`, `worker.json`, `freelancer.json`, `creator.json`,
  `business.json`, `mentor.json`, `teacher.json`: mode-specific priorities and
  contexts.

The corpus contains 1,119 documents: all 569 prior documents, exactly 500 new
context documents tagged `new-500`, plus 10 focused checklist/time correction
lessons that preserve clock expressions and sort timed tasks correctly, and 30
negative-intent lessons that keep company/founder questions out of workspace tools.
It also includes 10 web-fallback lessons for answering out-of-scope information
questions with sourced public-web research while protecting private workspace data.
Every document has a one-to-one `content_en` semantic pair tagged
`semantic-pair,vi-en`. During import, the English equivalent is appended to the
same RAG record as the Vietnamese rule. This keeps titles and source IDs stable
while allowing equivalent English queries to retrieve exactly the same behavior,
privacy boundaries, confirmation requirements, and factual-grounding rules.
Regenerate deterministically with `python scripts/build_bob_mode_corpus.py`.
Focused shared lessons include actual paired examples such as `in English`,
`both languages`, `the second one`, and mixed constraints such as
`except invoice`, rather than only generic multilingual tags.

## Import

```powershell
python scripts/train_bob.py .\docs\bob-training --tags "noi bo,quy tac,bob"
```

Use `--dry-run` first when checking document counts without writing to the DB.

To validate/import the labelled intent corpus separately:

```powershell
python scripts/train_bob_intents.py --dry-run
python scripts/train_bob_intents.py
```

Railway deploy imports every `modes/*.json` file automatically through
`scripts/deploy_postgres_schema.py` using one versioned source label per mode.
