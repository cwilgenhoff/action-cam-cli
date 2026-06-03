# Testing Guide

How we write tests in this project. The goal is a suite that **catches real
regressions, survives refactors, and reads like documentation**. Examples below are
from this repo, but the conventions are project-agnostic — copy this file into any
Python/pytest project.

> TL;DR: test **behavior, not implementation**; group tests in `Test*` classes by the
> unit under test; parametrize the rule; keep tests hermetic (mock the boundaries);
> commit small synthetic fixtures and keep real data local.

---

## 1. Test behavior, not implementation

Assert the **contract** a unit guarantees — never incidental internals.

**Don't**
- Assert exact opaque output strings ("golden strings"): they couple the test to
  internal naming/formatting and break on harmless refactors.
- Call private (`_helper`) functions directly — exercise them through the public API.
- Write tautologies / change-detectors (asserting a constant equals the same literal).
  They mirror the source, break on *any* change, and verify nothing.

**Do** — assert invariants and properties:
```python
# ❌ mirrors the source; breaks on a rename; proves nothing
assert NVENC_OUTPUT_ARGS == ["-c:v", "hevc_nvenc", "-preset", "p6", ...]

# ✅ the contract that actually matters
assert cmd[cmd.index("-pix_fmt") + 1] == "p010le"   # 10-bit pairing
assert cmd.count("-i") == n_inputs                   # one input per item
assert ("-y" in cmd) is force                        # force ⇒ overwrite
```

## 2. Spend coverage where the risk is

Test the **algorithm**, not the boilerplate — the core rules and the math. Aim
directly at **real failure modes and past regressions** (e.g. a cross-platform path
bug, a wrong pixel format, a known overshoot). A test that re-asserts a literal is
wasted; a test that pins a business rule is gold.

## 3. Parametrize the rule, not one example

The edge cases *are* the spec. Use `@pytest.mark.parametrize` over `input → expected`:
```python
@pytest.mark.parametrize("counters, expected", [
    ([12, 13, 14],    [[12, 13, 14]]),       # contiguous
    ([12, 13, 20, 21],[[12, 13], [20, 21]]), # a gap splits
    ([5],             [[5]]),                # single
    ([],              []),                   # empty
    ([10, 10],        [[10], [10]]),         # duplicate edge
])
def test_groups_by_consecutive_counter(self, make_clip, counters, expected): ...
```

## 4. Group with classes — the `describe` / `it` analog

Plain `Test*` classes act as `describe` blocks; `test_*` methods as `it`. Group **by
the unit under test**.
```python
class TestFilterGraph:          # describe('build_filter_graph')
    def test_concats_every_input(self): ...   # it('concats every input')
class TestLutPathQuoting: ...
```
Rules / gotchas (especially coming from Jest/Mocha):
- The class **must** be named `Test*`, and have **no `__init__`** (pytest skips
  classes with a constructor).
- **No `unittest.TestCase`** — plain classes keep pytest's plain `assert` and fixtures.
- Fixtures inject as method args, `self` first: `def test_x(self, make_clip, tmp_path):`.
- **No shared mutable state via `self`** — each test runs on a *fresh* instance (unlike
  a `describe` closure). Share setup through fixtures, not instance attributes.
- Want literal `describe()/it()` nesting? The `pytest-describe` plugin provides it — but
  plain classes need no dependency and are idiomatic; prefer them.

## 5. Hermetic & fast — design *for* testability

- **Separate pure logic from I/O** so the core needs no mocks. Keep pure builders/math
  in one module and side effects (subprocess, file/network) in another. Pure functions
  are the cheapest, highest-value tests.
- **Mock the boundaries** for the rest — stub subprocess, `monkeypatch` dependencies —
  so the suite runs anywhere with no external tools/hardware:
  ```python
  monkeypatch.setattr(pipeline, "check_dependencies", lambda *a, **k: [])
  ```
- **Raise, don't `sys.exit()`**, in library/domain code → testable with
  `pytest.raises(MyError)`; let the CLI layer translate exceptions into exit codes.
- Use built-in fixtures: `tmp_path` (filesystem), `capsys` (assert stdout/stderr).

## 6. Share setup via `conftest.py` factory fixtures

Prefer a **factory** fixture (returns a function) when tests need variations:
```python
# tests/conftest.py
@pytest.fixture
def make_clip():
    def _make(counter): return Clip(counter=counter, ...)
    return _make
```

## 7. Test data: synthetic + committed vs. real + local

- **Committed fixtures** (`tests/fixtures/`): tiny, hand-built, **deterministic** —
  known inputs that produce assertable numbers (e.g. a fixture with `5/10/10 m/s`
  speeds → exactly `18/36/36 km/h`).
- **Real / private data**: git-ignored (e.g. a `samples/` folder), **never committed**
  (privacy + size). CI must never depend on it.

## 8. Two distinct kinds of test

- **Unit / behavioral** (most of the suite) — fast, mocked, assert contracts.
- **Characterization / behavior-preservation** — for refactors: capture real output
  *before* the change and assert it is **byte-identical after** (e.g. diff a
  `--dry-run` command dump). This answers "did I change observable behavior?", which
  unit tests don't.

## 9. Verify against ground truth when you can

Don't trust your own math in a vacuum. If an authoritative source exists (a reference
implementation, an official report, a device's own output), assert against it — that's
how you catch "plausible but wrong" logic.

## 10. CI enforces it

Run the linter + `pytest` on a matrix that includes your **primary target OS**.
Cross-platform bugs (e.g. `/` vs `\` in a path assertion) hide on a single-OS runner.

---

## Agent checklist (before adding/changing a test)

1. Am I asserting a **contract**, or mirroring the implementation? (If the test would
   break on a behavior-preserving refactor, it's testing the wrong thing.)
2. Is this exercising the **public API**, not a private helper?
3. Is it a **rule** → parametrize the edge cases, not one happy-path example.
4. Is it in the right **`Test*` class** for its unit?
5. Is it **hermetic** (no real network/tools/hardware; mock the boundaries)?
6. If it needs data, is there a **small committed fixture** — and is any real data
   kept local/git-ignored?
7. For a refactor: is there a **before/after characterization** check?
