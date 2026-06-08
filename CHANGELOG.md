## v0.10.0 (2026-06-08)

### Feat

- **auth**: add Sign in with Apple (#50)
- **auth**: let users disconnect linked sign-in providers (#49)
- **auth**: server-verified logins and account linking (#48)

## v0.9.0 (2026-06-06)

### Feat

- **books**: create books and chapters from the carousels (#46)
- **admin**: support apple profile in user approval (#45)

### Fix

- **errors**: return correct status for unhandled http errors
- **security**: enable template autoescaping to prevent stored XSS (#47)

### Refactor

- **cache**: hash variable key segments

## v0.8.0 (2026-06-03)

### Feat

- **characters**: add permission_manage_npc setting (#41)
- **characters**: allow quick-creating NPCs and limit XP to players
- **characters**: add filters to character list card (#39)
- add system status footer for approved users (#37)

### Fix

- **character**: keep trait dots on one line
- improve mobile display of xp stats
- allow production mode to run locally during development

### Refactor

- **cache**: centralize API-response caching in lib/cache (#44)
- **characters**: defer visibility and type rules to the API (#40)
- **admin**: improve audit log card (#38)

### Perf

- **cache**: fetch reference catalogs in a single request
- **global-context**: remove eager book/chapter fan-out (#42)

## v0.7.1 (2026-05-23)

### Fix

- minor mobile improvements (#36)
- **diceroll**: use a full page on mobile (#35)
- decrease recent-rolls page count (#34)
- **nav**: show overflow items in priority nav More dropdown

## v0.7.0 (2026-04-27)

### Feat

- **character**: migrate to new campaign view
- **audit-log**: shared lazy-loaded audit log card (#30)
- **campaign**: add lazy-loaded Recent Dicerolls card (#28)
- campaign/book/chapter redesign (#27)
- redesign global header and campaign dashboard (#26)

### Fix

- **user**: remove back home button
- commit random fixes
- **campaign**: improve mobile card display

### Refactor

- **ui**: migrate remaining cards to surface-card utility (#29)

## v0.6.0 (2026-04-19)

### Feat

- **character-create**: surface autogen settings on selection cards (#25)
- **admin**: pending-approval indicator in global nav and sidebar (#24)
- **admin**: add autogen starting points to company settings (#23)
- **security**: serve robots.txt disallowing all bots

### Fix

- **mobile**: responsive layout fixes across key surfaces (#22)

## v0.5.0 (2026-04-15)

### Feat

- **api**: migrate to vclient v1.23 on-behalf-of pattern (#21)
- **security**: block scanner probes in before_request hook (#20)
- **admin**: redesign settings as admin section with audit log (#19)

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
