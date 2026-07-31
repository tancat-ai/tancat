# Jira Export — Sprint 47 Dashboard Features

**Project:** DASH  
**Sprint:** 47  
**Export date:** 2026-07-25

## DASH-1201: New Analytics Dashboard Widget [NEW FEATURE]

Add a customizable analytics dashboard widget that users can configure to
display key metrics (revenue, conversion rate, user signups). The widget
supports drag-and-drop positioning and resizing.

**Priority:** High  
**Components:** dashboard-ui, metrics-api, user-preferences

**Schema changes:**
- `dashboard_widgets`: NEW table with columns id, user_id, widget_type, config_json, position_x, position_y, width, height
- `user_preferences.dashboard_layout`: NEW field, JSONB, stores widget arrangement

## DASH-1198: Export Button Relocation [MODIFIED]

Move the "Export to CSV" button from the top toolbar to a dropdown menu in each
widget header. This reduces toolbar clutter and groups widget-specific actions
together.

**Priority:** Medium  
**Components:** dashboard-ui

## DASH-1195: Real-Time Data Refresh [MODIFIED]

Add a WebSocket-based real-time data refresh option to the dashboard. Currently,
data refreshes on page load only. Users can now toggle auto-refresh with
configurable intervals (30s, 60s, 5min).

**Priority:** High  
**Components:** dashboard-ui, websocket-service, metrics-api

## DASH-1180: Legacy Chart Library [REMOVED]

Remove the legacy Chart.js v2 dependency. All charts have been migrated to
Chart.js v4 as of Sprint 45. The old library is no longer bundled.

**Priority:** Medium  
**Components:** dashboard-ui, build-pipeline

## DASH-1175: Authentication Middleware [UNCHANGED]

The authentication middleware (JWT token validation) remains unchanged.
No modifications to the auth flow, token refresh, or session management.

**Priority:** Low  
**Components:** auth-middleware
