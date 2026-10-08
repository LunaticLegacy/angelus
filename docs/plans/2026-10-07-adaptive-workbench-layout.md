# Adaptive Workbench Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Angelus's three-column workbench adjustable, collapsible, and usable on narrow screens without changing its existing inspector data model.

**Architecture:** Keep the current CSS grid and inspector tabs, but expose left/right widths as CSS custom properties controlled by a small shell controller. Add accessible resize separators and collapse buttons, persist bounded preferences in local storage, and turn the Inspector into a drawer below the desktop breakpoint.

**Tech Stack:** Static HTML, CSS, ES modules, localStorage, Pointer Events, keyboard accessibility.

---

### Task 1: Add shell controls

**Files:** `frontend/templates/index.html`

- Add accessible collapse buttons to the sidebar and Inspector.
- Add two keyboard-operable vertical resize separators between the three columns.
- Add a mobile Inspector open button and drawer backdrop.

### Task 2: Implement layout state

**Files:** `frontend/static/ui/shell.js`

- Store bounded sidebar/Inspector widths and collapsed state.
- Support pointer dragging, keyboard arrows/Home/End, double-click reset, and Escape to close the mobile drawer.
- Keep focus visible and return focus to the opener after closing the drawer.

### Task 3: Style desktop, collapsed, and mobile states

**Files:** `frontend/static/app.css`

- Replace fixed grid widths with CSS variables.
- Style resize handles, collapse controls, icon rails, drawer backdrop, and narrow-screen behavior.
- Preserve the existing visual language and avoid nested page scrolling.

### Task 4: Verify

- Run `node --check frontend/static/ui/shell.js` and `node --check frontend/static/app.js`.
- Inspect the diff and confirm no unrelated dirty files were changed.
