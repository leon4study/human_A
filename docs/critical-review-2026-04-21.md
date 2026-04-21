# Critical Review Memo

Date: 2026-04-21

## Reviewed scope

- `frontend/src/app/layout/DashboardFrame.tsx`
- `frontend/src/app/components/side/ZoneStatusPanel.tsx`
- `frontend/src/app/components/side/ZoneCauseTopPanel.tsx`
- `frontend/src/app/components/side/KpiPanel.tsx`
- `frontend/src/app/styles/panel.css`

## Findings and fixes

1. `DashboardFrame` kept `selectedZoneId` only in local state.
   When websocket data replaced `zoneItems`, the old selection could become invalid and downstream panels would render inconsistent or empty content.
   Fix: synchronize `selectedZoneId` with the latest `zoneItems` and reset safely when the list is empty.

2. Top device buttons were hard-coded to `1호기`, `2호기`, `3호기`.
   This could drift from actual backend data and gave users a misleading UI when the zone list changed.
   Fix: render the buttons from `zoneItems` and use them as an actual zone selector.

3. `ZoneStatusPanel` assumed at least one zone exists.
   With an empty array, `worstZone.id` and `goldenZone.id` would crash at render time.
   Fix: add an explicit empty state and prevent duplicate `Worst`/`Golden` badges for a single-item list.

4. `ZoneCauseTopPanel` silently rendered nothing when the selected zone had no matching cause data.
   That looked like a broken panel rather than a valid "no data" condition.
   Fix: add a clear empty-state message and clean up the title when no zone is selected.

5. `KpiPanel` depended on three hard-coded KPI ids.
   Any backend/schema change in ids would incorrectly show "데이터가 없습니다." even if valid KPI data existed.
   Fix: make the panel data-driven using each item's `size` and `color` fields instead of fixed ids.

## Verification

- Run `npm run build` in `frontend`
- Run `npm run lint` in `frontend`

## Notes

- The repository has many unrelated modified files already present, so this review was limited to the dashboard data/panel flow around the currently active files.
