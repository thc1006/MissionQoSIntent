# R2 — a tenant may not request a criticality band above its entitlement.
package missionqos.guard_test

import data.missionqos.guard

# BOUNDARY (always allowed): the exact entitled band (city-ops -> incident-verification).
test_criticality_allow_equal_band if {
	guard.allow with input as contract("city-ops", [wl({"missionClass": "incident-verification"})])
}

# A band below the entitlement is allowed.
test_criticality_allow_lower_band if {
	guard.allow with input as contract("city-ops", [wl({"missionClass": "historical-analysis"})])
}

# BOUNDARY (never allowed): one band above the entitlement (city-ops -> emergency-routing).
test_criticality_deny_one_band_above_entitlement if {
	inp := contract("city-ops", [wl({"missionClass": "emergency-routing"})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "criticality")
}

# A higher-entitled tenant (ops-admin -> emergency-routing) may request the top band.
test_criticality_allow_entitled_top_band if {
	guard.allow with input as contract("ops-admin", [wl({"missionClass": "emergency-routing"})])
}
