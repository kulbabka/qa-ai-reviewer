# Projects

Each subdirectory under `projects/` is a self-contained project configuration.

## Directory structure

```
projects/
└── your_project/
    ├── context.md          # QA scope and what is/isn't being reviewed
    ├── glossary.md         # Term definitions for consistent language in findings
    ├── rules.md            # Review focus, evidence requirements, priority rules
    └── product_context.md  # Product description, audience, and feature under analysis
```

---

## File descriptions

### `context.md` *(required)*
Defines the QA scope for this project.
Used by: Mode 1 (Requirement review), Mode 2 (Flow → test cases), Mode 3 (UX review)

### `glossary.md` *(optional)*
Product and domain terminology that findings should use consistently.
Used by: Mode 1, Mode 3

### `rules.md` *(optional)*
Controls what the AI focuses on and what it deprioritizes.
Used by: Mode 1, Mode 3

### `product_context.md` *(optional, required for Mode 3)*
Provides product and feature background needed for UX analysis.

Must include:
- What the product is (category, value proposition)
- Business model (plan tiers, limits)
- Target audience (technical level, mental model)
- Feature under analysis (purpose, location, config options, user goals)

Optional: competitor comparison, feature-specific glossary.
Used by: **Mode 3 (UX / Feature review) only**

---

## Adding a new project

1. Create `projects/my_project/`
2. Add `context.md` (required)
3. Add `product_context.md` if using Mode 3
4. Add `glossary.md` and `rules.md` as needed

---

## Included projects

| Project              | Description                                        |
|----------------------|----------------------------------------------------|
| `test_project`       | Empty template — starting point for new projects   |
| `coupler_scheduler`  | Coupler.io Automatic Data Refresh scheduler review |
