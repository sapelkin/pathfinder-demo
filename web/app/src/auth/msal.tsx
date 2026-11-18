import { lazy, Suspense, type ReactNode } from 'react'
import { Spinner } from '@fluentui/react-components'
import { IS_LOCAL } from '../api/mode'

/// Sign-in is off locally (VITE_AUTH_DISABLED=1, the default), in the backend-free build, and without a client id.
/// MSAL is loaded only when it is on, so it never ships in the local bundle.
export const AUTH_DISABLED = IS_LOCAL || (import.meta.env.VITE_AUTH_DISABLED ?? '1') === '1' || !import.meta.env.VITE_MSAL_CLIENT_ID

const MsalGate = lazy(() => import('./msalGate'))

export function AuthProvider({ children }: { children: ReactNode }) {
  if (AUTH_DISABLED) return <>{children}</>
  return (
    <Suspense fallback={<div className="auth-gate"><Spinner label="Signing in…" /></div>}>
      <MsalGate>{children}</MsalGate>
    </Suspense>
  )
}
