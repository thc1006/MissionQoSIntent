# MissionQoSIntent policy guard.
# A contract is admitted only if no cross-tenant invariant is violated (no false-allow).
package missionqos.guard

# A contract is admitted only when no deny reason fires.
default allow := false

allow if count(deny) == 0

# Foundational safety: an unknown tenant has no entitlement basis, so reject it. This keeps the
# entitlement rules (R1/R2/R3) from silently passing when the tenant is absent from data.
deny contains msg if {
	t := object.get(input, ["metadata", "tenant"], "")
	not data.missionqos.tenants[t]
	msg := sprintf("unknown tenant %q", [t])
}
