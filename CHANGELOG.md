## v0.4.0 (2026-04-10)

### Feat

- **ui**: add hero image and update landing page layout (#18)
- **ui**: add inline editing for campaign danger/desperation badges (#17)
- **ui**: add back-navigation links to PageHeader (#16)

### Fix

- **ui**: auto-close dropdown menus on outside click (#15)

### Refactor

- **proxy**: replace vendor-specific middleware with generic IP resolution (#14)

## v0.3.2 (2026-04-09)

### Fix

- **traits**: replace inline script redirects with HX-Redirect (#13)
- **book**: return card fragment on edit cancel (#12)
- **security**: replace inline JS with Alpine/HTMX (#11)
- **auth**: add POST method to logout route (#10)

## v0.3.1 (2026-04-09)

### Fix

- **security**: resolve real client IP (#9)

## v0.3.0 (2026-04-09)

### Feat

- multi-company support (#8)
- replace theme picker with light/dark toggle (#6)

### Fix

- **admin**: improve notification for pending user approvals
- **book**: fix chapters card when switching books (#7)
- auth connection errors (#5)

## v0.2.1 (2026-04-08)

### Fix

- **auth**: trust proxy headers so OAuth callbacks use https (#3)

### Refactor

- slim down app.py and reorganize lib/ (#4)

## v0.2.0 (2026-04-08)

### Feat

- add initial feature set
