# R1 — summed guaranteed throughput must not exceed the tenant's entitled capacity.
package missionqos.guard_test

import data.missionqos.guard

# BOUNDARY (allowed): the summed floor exactly equals the entitlement (city-ops -> 500 rps).
test_throughput_allow_sum_equal_entitlement if {
	guard.allow with input as contract("city-ops", [wl({"throughputFloorRps": 500})])
}

# BOUNDARY (denied): one rps above the entitlement.
test_throughput_deny_sum_above_entitlement if {
	inp := contract("city-ops", [wl({"throughputFloorRps": 501})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "throughput")
}

# The floor is summed ACROSS workloads: 250 + 250 == 500 -> allowed.
test_throughput_allow_sum_across_workloads if {
	inp := contract("city-ops", [wl({"throughputFloorRps": 250}), wl({"throughputFloorRps": 250})])
	guard.allow with input as inp
}

# Summed across workloads above the entitlement (300 + 300 = 600) -> denied.
test_throughput_deny_sum_across_workloads if {
	inp := contract("city-ops", [wl({"throughputFloorRps": 300}), wl({"throughputFloorRps": 300})])
	not guard.allow with input as inp
}

# Workloads without a throughput floor contribute 0 -> allowed.
test_throughput_allow_when_no_floor if {
	no_floor := object.remove(default_workload, {"throughputFloorRps"})
	guard.allow with input as contract("city-ops", [no_floor])
}
