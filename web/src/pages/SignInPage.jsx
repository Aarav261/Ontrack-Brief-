import { SignIn } from '@clerk/clerk-react'

export default function SignInPage() {
  return (
    <div className="centered">
      <SignIn
        routing="path"
        path="/sign-in"
        signUpUrl="/sign-up"
        forceRedirectUrl="/"
      />
    </div>
  )
}
