# Coding Standards

## Oil Spill Attribution System

This document defines the coding standards for the project.

The goal is to keep code:

- Consistent
- Readable
- Testable
- Maintainable
- Modular
- Scientifically reliable

These standards apply to all project code, including AI-generated code.

---

# 1. General Principles

Follow these rules:

1. Prefer simple code over clever code.
2. Keep functions small and focused.
3. Give variables meaningful names.
4. Avoid duplicate logic.
5. Avoid unnecessary abstraction.
6. Keep modules independent.
7. Validate external inputs.
8. Write tests for important behavior.
9. Never hide scientific assumptions.
10. Do not optimize before identifying a real bottleneck.

---

# 2. Python Version

The project targets:

```text
Python 3.13