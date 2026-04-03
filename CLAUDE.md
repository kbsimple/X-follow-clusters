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

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
