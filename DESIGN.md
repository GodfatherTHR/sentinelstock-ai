# SentinelStock AI — UI Direction

## Mode

Operate. The first surface is a warehouse/procurement control room where the user prioritizes risk, inspects evidence, and approves bounded actions.

## Visual world

Cold-chain manifest: dark graphite panels, ice-blue structure, warm signal orange for urgency, mint for verified stability, and soft paper-white for readable data. The interface borrows from freight-yard wayfinding boards and refrigerated shipping manifests: hairline seams, compact labels, tabular numerals, and status strips that look operational rather than ornamental.

## First viewport

The left rail holds the operating areas. The main frame opens with a “Network pulse” header, four key metrics, a warehouse signal map, and a split lower zone: active recommendations on the left and demand/sentiment evidence on the right. The user should understand “where is risk, why is it moving, and what can I approve?” in one scan.

## Material and typography

- Ground: #071014 / #0B171C; panels: #10242A; seams: #22434A.
- Verified: ice/mint #8BE4C0; attention: signal orange #FF9C58; critical: coral #FF6B62; neutral ink: #E9F3EF; muted ink: #8EA7A6.
- Use a compact sans for UI text and a monospace face for metrics, IDs, dates, and quantities.
- Avoid gradients, ornamental shadows, and color-only severity cues.

## Interaction grammar

- Cards expose evidence in place; actions use explicit labels.
- Risk badges always include text: LOW, MEDIUM, HIGH, CRITICAL.
- Recommendation actions are “Review”, “Approve”, and “Reject”, with human approval language visible.
- Motion is short and purposeful: reveal, pulse, and map pings; honor reduced motion.

## Responsive behavior

The rail collapses to a top strip under 920px. The map and insights stack under 760px. Dense tables keep horizontal scroll rather than truncating SKU, status, or quantity.
