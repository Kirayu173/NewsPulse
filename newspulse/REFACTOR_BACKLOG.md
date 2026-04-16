# Refactor Backlog

Last updated: 2026-04-14

This file records the next architecture simplification topics for NewsPulse.
They are intentionally kept at the project root so we can review and execute them one by one.

## Pending Topics

### 1. Move config fully inside the project
- Goal: make configuration ownership fully internal to NewsPulse.
- Focus:
  - clarify which config files are runtime config, which are prompts, which are defaults
  - unify config lookup rules and reduce ambiguous external dependency behavior
  - prepare for later packaging / relocation / standalone operation
- Expected outcome:
  - simpler config model
  - less hidden path dependency
  - easier bootstrap and deployment consistency
- Status: recorded, pending detailed design

### 2. Unify RSS and hotlist into one data source layer
- Goal: stop treating RSS and hotlist as two parallel source systems at the architecture level.
- Focus:
  - design a unified source abstraction
  - align fetch / normalize / storage / analysis input formats
  - make downstream pipeline consume one source-layer contract
- Expected outcome:
  - one source domain model
  - less branching in pipeline/report/AI logic
  - easier future source expansion
- Status: recorded, pending detailed design

### 3. Strengthen the AI workflow and remove redundant AI modules
- Goal: make AI a native first-class workflow rather than several loosely attached features.
- Focus:
  - redesign the AI workflow around native integration points
  - merge or remove redundant AI-related modules and duplicated glue code
  - improve consistency across filter / analysis / translation stages
- Expected outcome:
  - cleaner AI architecture
  - stronger workflow continuity
  - less repeated prompt/config/runtime plumbing
- Status: recorded, pending detailed design

### 0. Split services and shrink the container
- Goal: further split the current orchestration layer into smaller services.
- Focus:
  - reduce the size and responsibility of `newspulse/pipeline/news_analyzer.py`
  - reduce the facade/container responsibility of `newspulse/context.py`
  - make fetch / analyze / report / notify stages independently composable
- Expected outcome:
  - clearer service boundaries
  - lower coupling across modules
  - easier testing and later deletion of legacy glue logic
- Status: recorded, pending detailed design

## Execution Rule
- We will review and decide these items one by one.
- If a later design requires broad replacement, old logic should be removed cleanly instead of being kept as parallel paths.
