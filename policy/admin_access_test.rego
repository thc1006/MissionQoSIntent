# R4 — no privileged adminAccess for non-admin tenants (DRA Admin Access GA, K8s v1.36).
package missionqos.guard_test

import data.missionqos.guard

# ALWAYS allowed boundary: a non-admin tenant that requests no adminAccess.
test_admin_access_allow_non_admin_without_flag if {
	guard.allow with input as contract("city-ops", [wl({"adminAccess": false})])
}

# NEVER allowed boundary: a non-admin tenant that requests adminAccess.
test_admin_access_deny_non_admin_with_flag if {
	inp := contract("city-ops", [wl({"adminAccess": true})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "adminAccess")
}

# Allowed: an admin tenant may request adminAccess.
test_admin_access_allow_admin_tenant_with_flag if {
	guard.allow with input as contract("ops-admin", [wl({"adminAccess": true})])
}
