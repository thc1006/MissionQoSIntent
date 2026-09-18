# R3 — a deadline SLO requires a matching (capable, known) device class.
package missionqos.guard_test

import data.missionqos.guard

# BOUNDARY (allowed): deadline exactly at the device-class minimum (gpu-24g -> 500ms).
test_deadline_allow_at_device_minimum if {
	inp := contract("city-ops", [wl({"slo": {"deadline": 500}, "resourceClass": "gpu-24g"})])
	guard.allow with input as inp
}

# BOUNDARY (denied): deadline one ms below the device-class minimum.
test_deadline_deny_below_device_minimum if {
	inp := contract("city-ops", [wl({"slo": {"deadline": 499}, "resourceClass": "gpu-24g"})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "device")
}

# An unknown device class is rejected (no matching device).
test_deadline_deny_unknown_device_class if {
	inp := contract("city-ops", [wl({"resourceClass": "gpu-8g"})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "device class")
}

# Below the system-wide minimum service time -> never serviceable, denied.
test_deadline_deny_below_system_minimum if {
	inp := contract("city-ops", [wl({"slo": {"deadline": 10}, "resourceClass": "gpu-40g"})])
	not guard.allow with input as inp
	some msg in guard.deny with input as inp
	contains(msg, "system minimum")
}
