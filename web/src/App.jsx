import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import SignInPage from './pages/SignInPage.jsx'
import SignUpPage from './pages/SignUpPage.jsx'
import Unsubscribe from './pages/Unsubscribe.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />
      <Route path="/unsubscribe" element={<Unsubscribe />} />
    </Routes>
  )
}
