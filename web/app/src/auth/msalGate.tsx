import { useEffect, type ReactNode } from 'react'
import { PublicClientApplication, InteractionRequiredAuthError, type Configuration } from '@azure/msal-browser'
import { MsalProvider, useMsal, useIsAuthenticated } from '@azure/msal-react'
import { Button, Spinner } from '@fluentui/react-components'
import { setTokenProvider } from '../api/client'

const config: Configuration = {
  auth: {
    clientId: (import.meta.env.VITE_MSAL_CLIENT_ID as string) || '00000000-0000-0000-0000-000000000000',
    authority: (import.meta.env.VITE_MSAL_AUTHORITY as string) || 'https://login.microsoftonline.com/common',
    redirectUri: typeof window !== 'undefined' ? window.location.origin : undefined,
  },
  cache: { cacheLocation: 'sessionStorage' },
}
const scopes = ((import.meta.env.VITE_API_SCOPE as string) || 'User.Read').split(/[ ,]+/).filter(Boolean)

let pca: PublicClientApplication | null = null
function client(): PublicClientApplication {
  if (!pca) pca = new PublicClientApplication(config)
  return pca
}

function Gate({ children }: { children: ReactNode }) {
  const { instance, inProgress, accounts } = useMsal()
  const authed = useIsAuthenticated()

  useEffect(() => {
    if (!authed) { setTokenProvider(null); return }
    setTokenProvider(async () => {
      const account = accounts[0] ?? instance.getActiveAccount()
      if (!account) return null
      try {
        const r = await instance.acquireTokenSilent({ scopes, account })
        return r.accessToken
      } catch (e) {
        if (e instanceof InteractionRequiredAuthError) await instance.acquireTokenRedirect({ scopes, account })
        return null
      }
    })
    return () => setTokenProvider(null)
  }, [authed, accounts, instance])

  if (inProgress !== 'none') {
    return <div className="auth-gate"><Spinner label="Signing in…" /></div>
  }
  if (!authed) {
    return (
      <div className="auth-gate">
        <h1>Pathfinder</h1>
        <p>Sign in with your work account to open the demo ED.</p>
        <Button appearance="primary" onClick={() => instance.loginRedirect({ scopes })}>Sign in</Button>
      </div>
    )
  }
  return <>{children}</>
}

export default function MsalGate({ children }: { children: ReactNode }) {
  const instance = client()
  return (
    <MsalProvider instance={instance}>
      <Gate>{children}</Gate>
    </MsalProvider>
  )
}
