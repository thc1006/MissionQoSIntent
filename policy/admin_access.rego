# R4 — no privileged adminAccess for non-admin tenants.
# DRA "Admin Access" is GA in K8s v1.36; only admin tenants may request it.
package missionqos.guard

# True only when the contract's tenant is a known admin tenant.
default is_admin := false

is_admin if data.missionqos.tenants[input.metadata.tenant].admin == true

deny contains msg if {
	some w in input.spec.workloads
	w.adminAccess == true
	not is_admin
	msg := sprintf(
		"workload %q requests adminAccess but tenant %q is not an admin",
		[w.missionClass, input.metadata.tenant],
	)
}
