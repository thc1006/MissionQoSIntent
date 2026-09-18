# Foundational guard tests: the allow gate and the unknown-tenant safety deny.
package missionqos.guard_test

import data.missionqos.guard

# A fully-valid contract for a known tenant is admitted.
test_allow_valid_contract if {
	guard.allow with input as contract("city-ops", [default_workload])
}

# An unknown tenant has no entitlement basis, so it must be denied (no silent pass).
test_deny_unknown_tenant if {
	inp := contract("ghost-tenant", [default_workload])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "unknown tenant")
}

# Missing metadata.tenant is also treated as unknown -> denied.
test_deny_missing_tenant if {
	inp := {"metadata": {"mission": "m"}, "spec": {"workloads": [default_workload]}}
	not guard.allow with input as inp
}

# Aggregation: a fully-valid multi-workload contract for an entitled tenant is admitted.
test_allow_valid_multi_workload_contract if {
	inp := contract("ops-admin", [
		wl({
			"missionClass": "emergency-routing", "priority": 100,
			"slo": {"deadline": 500}, "resourceClass": "gpu-40g", "throughputFloorRps": 600,
		}),
		wl({
			"missionClass": "city-monitoring", "priority": 50,
			"slo": {"deadline": 5000}, "resourceClass": "gpu-24g", "throughputFloorRps": 300,
		}),
	])
	guard.allow with input as inp
	count(guard.deny) == 0 with input as inp
}

# Aggregation: a contract violating R1-R4 at once is denied with a reason per invariant.
test_deny_reports_all_violated_invariants if {
	inp := contract("city-ops", [wl({
		"missionClass": "emergency-routing", # R2: above city-ops entitlement
		"throughputFloorRps": 999, # R1: above the 500 rps entitlement
		"slo": {"deadline": 10}, # R3: below the system minimum
		"resourceClass": "gpu-8g", # R3: unknown device class
		"adminAccess": true, # R4: non-admin requesting adminAccess
	})])

	not guard.allow with input as inp
	reasons := guard.deny with input as inp
	count(reasons) >= 4
	some r_tput in reasons
	contains(r_tput, "throughput")
	some r_crit in reasons
	contains(r_crit, "criticality")
	some r_dev in reasons
	contains(r_dev, "device class")
	some r_admin in reasons
	contains(r_admin, "adminAccess")
}
