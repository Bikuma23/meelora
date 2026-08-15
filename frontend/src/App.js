import "./App.css";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LanguageProvider } from "./context/LanguageContext";
import Login from "./components/Login";
import ResetPassword from "./components/ResetPassword";
import Activate from "./components/Activate";
import Layout from "./components/Layout";

function Shell() {
  const { user } = useAuth();
  const path = window.location.pathname.replace(/\/+$/, "");
  // Public password-reset screen reached from the email link.
  if (path === "/reset-password") return <ResetPassword />;
  // Public activation screen reached from an invitation link.
  if (path === "/activate") return <Activate />;
  if (user === null)
    return <div className="flex min-h-screen items-center justify-center bg-[#0E1526] font-mono-data text-sm text-slate-400">Chargement…</div>;
  if (!user) return <Login />;
  return <Layout />;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <LanguageProvider>
          <Shell />
          <Toaster position="top-right" richColors />
        </LanguageProvider>
      </AuthProvider>
    </div>
  );
}

export default App;
