import { useEffect, useState } from 'react'
import { versionAtLeast } from '../utils/version'

// Polls /api/version once on mount. Returns the server's minimum required
// version when the running extension is too old (so the app can render the
// update wall), otherwise null. Failures are swallowed — a missed check should
// never block the popup.
export function useVersionGate(currentVersion) {
  const [minVersion, setMinVersion] = useState(null)

  useEffect(() => {
    fetch(`${window.APP_URL}/api/version`)
      .then((r) => r.json())
      .then((d) => {
        if (d.min_required && !versionAtLeast(currentVersion, d.min_required)) {
          setMinVersion(d.min_required)
        }
      })
      .catch(() => {})
  }, [currentVersion])

  return minVersion
}
