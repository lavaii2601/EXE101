# Bob training documents

Bob does not fine-tune a base model in this repo. These files are imported into
the FlowMate knowledge base through `scripts/train_bob.py` and used as RAG
context during chat.

## Files

- `workflow-study-email-schedule.json`: core workflow, Student mode, email,
  schedule, checklist, and feature-playbook rules.
- `email-150-knowledge.json`: 150 email-specific behavior rules for Gmail
  connection, search, summaries, triage, replies, safety, attachments, and
  email-to-calendar/checklist workflows.
- `bob-100-feature-cases.json`: 100 concrete behavior cases that teach Bob how
  to handle common FlowMate actions and edge cases.
- `english-semantics-cases.json`: English intent semantics, phrasing, time
  expressions, confirmation words, and mixed-language rules.

## Import

```powershell
python scripts/train_bob.py .\docs\bob-training --tags "noi bo,quy tac,bob"
```

Use `--dry-run` first when checking document counts without writing to the DB.

Railway deploy also imports `email-150-knowledge.json` automatically through
`scripts/deploy_postgres_schema.py` using source `bob-email-150`.
