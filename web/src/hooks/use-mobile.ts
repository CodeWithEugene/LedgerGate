import * as React from "react"

const MOBILE_BREAKPOINT = 768

// Rewritten from the shadcn default, which set state directly inside an effect
// and tripped react-hooks/set-state-in-effect. The viewport is an external
// store, so useSyncExternalStore is the fit; the server snapshot is false
// because there is no viewport to measure during SSR.
function subscribe(onChange: () => void) {
  const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribe,
    () => window.innerWidth < MOBILE_BREAKPOINT,
    () => false,
  )
}
