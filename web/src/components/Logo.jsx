// The Ontracker sparkle mark, in the site accent blue (#4361ee). Inline SVG so
// it scales crisply and needs no asset request. Geometry matches the extension
// icon (extension/public/icons/icon.svg) and popup header.
export default function Logo({ size = 30, className }) {
  const id = `ontracker-logo-cut-${size}`
  return (
    <svg
      className={className}
      viewBox="0 0 128 128"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="128" height="128">
        <circle cx="64" cy="64" r="58" fill="#fff" />
        <path d="M64 15 Q64 64 89 64 Q64 64 64 113 Q64 64 39 64 Q64 64 64 15 Z" fill="#000" />
        <rect x="2" y="62.5" width="124" height="3" fill="#000" />
      </mask>
      <rect width="128" height="128" fill="#4361ee" mask={`url(#${id})`} />
    </svg>
  )
}
