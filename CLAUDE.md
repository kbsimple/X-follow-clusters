<!-- GSD:project-start source:PROJECT.md -->
## Project

**X Following Organizer**

A Python tool that reads the `follower.js` file from an X data archive export, enriches each followed account with profile data from the X API and profile page scraping, clusters followers into semi-automated categorized lists, and creates those lists as native X API lists. The user reviews and approves clusters before they become lists, with an option to enable full automation after trust is established.

**Core Value:** Transform a flat following list into organized, named X API lists that make it easy to reference and follow groups of similar people.

### Constraints

- **Tech Stack**: Python
- **Output**: Native X API lists (intermediate files allowed, final output must be X API lists)
- **Data Collection**: Rich profile data via X API + profile page scraping (not just basic API fields)
- **API Credentials**: X API authentication not yet obtained — must be factored into implementation plan
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.

### Commit Authorship

All commits must be authored by **Faiser** with email **keepbreakfastsimple@gmail.com**. Before creating a commit, set the environment variables:

```bash
export GIT_AUTHOR_NAME='Faiser'
export GIT_AUTHOR_EMAIL='keepbreakfastsimple@gmail.com'
export GIT_COMMITTER_NAME='Faiser'
export GIT_COMMITTER_EMAIL='keepbreakfastsimple@gmail.com'
```

Alternatively, configure the repo locally so rebasing never introduces the wrong author again:

```bash
git config --local author.name 'Faiser'
git config --local author.email 'keepbreakfastsimple@gmail.com'
git config --local committer.name 'Faiser'
git config --local committer.email 'keepbreakfastsimple@gmail.com'
```
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work
- `/gsd:next` for advancing between phases (always use this before starting a new phase)

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

### Phase Completion Gate

**A phase is done when ALL of these are true:**
1. All `*-PLAN.md` files have corresponding `*-SUMMARY.md` files (ground truth)
2. All relevant tests pass via `.venv/bin/python -m pytest tests/`
3. Git history contains implementation commits for the phase
4. ROADMAP.md and STATE.md are updated to reflect completion

**Never assume a prior phase is incomplete.** If implementation commits exist in git history, the phase is done — do not re-execute it. Verify via `git log --oneline | grep -E "phase|plan"` and test suite before declaring work pending.

### Phase Advance Protocol

When asked to "continue", "advance", or "make progress":
1. Run `/gsd-next` first — it checks what's done, what blocks, and routes to next action
2. Do not skip `/gsd-next` in favor of direct execution
3. Verify prior phase completeness via test suite + git history before starting dependent phases
4. Check `.planning/phases/{phase}/` for all expected `*-SUMMARY.md` files — their existence is the ground truth for plan completion
5. Keep ROADMAP.md and STATE.md in sync before every session end
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
