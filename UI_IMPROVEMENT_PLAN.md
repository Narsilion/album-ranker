# UI Improvement Plan

## Summary

Improve the server-rendered Album Ranker UI by tightening accessibility, responsive behavior, maintainability, and day-to-day usability without changing the app's route model or data model.

The highest-value work is to fix invalid nested interactive controls in album cards, add keyboard-visible focus states and live status announcements, improve mobile layouts, and replace repeated inline styles with reusable UI classes.

## Priority Improvements

1. Fix interactive controls inside album card links.
   - Album cards currently render as anchor elements that contain buttons for rating, bookmark, and listened actions.
   - Convert album cards to non-link containers with dedicated links for cover/title, or move action buttons outside the anchor.
   - Preserve current click behavior: opening album details from the cover/title area, while action buttons only perform their own action.

2. Add visible keyboard focus states.
   - Add a shared `:focus-visible` style for links, buttons, inputs, selects, textareas, tabs, letter filters, star buttons, and compact icon buttons.
   - Use a clear accent outline or box shadow that works across all dark themes.
   - Avoid layout shift when focus appears.

3. Improve responsive behavior.
   - Keep the existing `980px` breakpoint, then add smaller-screen rules for phone widths.
   - Make detail headers, toolbars, filters, alphabet filters, track rows, list rows, and action clusters wrap predictably.
   - Ensure long URLs, long artist names, and long album titles do not squeeze controls or overflow panels.

4. Replace repeated inline styles with reusable classes.
   - Introduce shared classes for common layout patterns: panel headers, toolbars, action rows, compact inputs, URL rows, status rows, danger zones, and empty states.
   - Move repeated `style="..."` snippets out of page renderers where practical.
   - Keep the app server-rendered in `ui.py`; do not introduce a frontend framework.

5. Make status messages accessible.
   - Add `role="status"` and `aria-live="polite"` to save/import/refresh/generate status elements.
   - Add a distinct error state style for failed actions.
   - Keep current text feedback, but make success, loading, cancelled, and error states visually consistent.

6. Clarify destructive actions.
   - Move destructive controls like `Delete Artist`, `Delete Album`, and list/genre deletion into clearer danger areas or visually separated action groups.
   - Keep confirmation dialogs, but make the surrounding UI communicate that deletion is destructive before the dialog appears.

7. Improve touch support for hover-only actions.
   - Avoid hiding important actions behind hover-only cover overlays on touch devices.
   - Keep bookmark/listened/rating actions discoverable through always-visible compact buttons or a visible actions row/menu.

8. Tighten operational page headers.
   - Reduce large hero treatment on dense workflow pages where users repeatedly manage albums, artists, genres, lists, and settings.
   - Prefer compact headers with page title, count, primary action, and short supporting text.
   - Preserve the dark theme and current visual identity.

9. Improve filter UX.
   - Show result counts such as `Showing 20 of 143`.
   - Add clear filter/reset controls for album and artist filters.
   - Add explicit empty states when filters return no matches.
   - Widen artist search where practical and keep filter controls usable on mobile.

10. Upgrade collapsible controls and tabs.
    - Add `aria-expanded` and `aria-controls` to show/hide controls.
    - Use consistent selected state handling for tabs and segmented controls.
    - Keep labels synchronized with state, such as `Show Tools`/`Hide Tools`.

## Implementation Notes

- Primary work should happen in `src/album_ranker/ui.py`.
- Avoid editing generated `build/lib/album_ranker/` files directly.
- If behavior changes require API support, update `src/album_ranker/app.py` and tests together.
- Keep tool panels collapsed by default where the app already follows that pattern.
- Do not move album import back to the shared albums page; artist-scoped album import belongs on dedicated artist pages.

## Test Plan

- Run the existing test suite:
  ```bash
  source .venv/bin/activate
  pytest
  ```
- Add or update `tests/test_api.py` coverage for any HTML structure that changes public UI behavior.
- Manually verify at desktop and narrow mobile widths:
  - album cards open details only from intended link areas;
  - bookmark/listened/rating controls do not navigate;
  - filters wrap cleanly and show correct counts;
  - collapsible panels expose correct labels and ARIA state;
  - status messages appear for saving, importing, refreshing, cancelling, and errors.

## Assumptions

- The app remains a server-rendered FastAPI app with inline HTML/CSS/JavaScript in `ui.py`.
- The dark theme remains the default and primary visual direction.
- Improvements should preserve current workflows and routes unless a specific task says otherwise.
- Accessibility and responsive fixes should be prioritized before purely cosmetic polish.
