// Semantic-ish version comparison for the extension update gate.

/** Returns true if `current` is at least `required` (both dot-separated strings). */
export function versionAtLeast(current, required) {
  const a = String(current).split('.').map(Number)
  const b = String(required).split('.').map(Number)
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const ai = a[i] ?? 0
    const bi = b[i] ?? 0
    if (ai > bi) return true
    if (ai < bi) return false
  }
  return true
}
