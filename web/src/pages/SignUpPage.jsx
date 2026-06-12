import { SignUp } from '@clerk/clerk-react'

export default function SignUpPage() {
  return (
    <div className="centered">
      <SignUp
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        forceRedirectUrl="/"
      />
    </div>
  )
}
