# Bob training documents

Bob does not fine-tune a base model in this repo. These files are imported into
the FlowMate knowledge base through `scripts/train_bob.py` and used as RAG
context during chat.

In addition, `services/bob_training_cases.py` generates exactly 500 labelled
phrases for every executable tool intent (currently 12 intents / 6,000 cases).
Unlike the passive RAG documents, this corpus trains Bob's built-in offline
classifier and is also imported in compact 50-case batches during deployment.

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
Regenerate deterministically with `python scripts/build_bob_mode_corpus.py`.

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
