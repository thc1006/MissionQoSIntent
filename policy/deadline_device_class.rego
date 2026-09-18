# R3 — a deadline SLO requires a matching device class.
package missionqos.guard

# R3a — the requested resourceClass must be a known device class.
deny contains msg if {
	some w in input.spec.workloads
	rc := object.get(w, "resourceClass", "")
	not data.missionqos.system.device_classes[rc]
	msg := sprintf("workload resourceClass %q is not a known device class", [rc])
}

# R3b — the deadline must be at or above the system-wide minimum service time.
deny contains msg if {
	some w in input.spec.workloads
	w.slo.deadline < data.missionqos.system.min_service_time_ms
	msg := sprintf(
		"workload deadline %dms is below the system minimum service time %dms",
		[w.slo.deadline, data.missionqos.system.min_service_time_ms],
	)
}

# R3c — the chosen device class must be able to meet the deadline.
deny contains msg if {
	some w in input.spec.workloads
	dc := data.missionqos.system.device_classes[w.resourceClass]
	w.slo.deadline < dc.min_deadline_ms
	msg := sprintf(
		"workload deadline %dms is below device %q minimum %dms",
		[w.slo.deadline, w.resourceClass, dc.min_deadline_ms],
	)
}
