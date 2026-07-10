import "./App.css";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./components/Login";
import Layout from "./components/Layout";

function Shell() {
  const { user } = useAuth();
  if (user === null)
    return <div className="flex min-h-screen items-center justify-center bg-[#0E1526] font-mono-data text-sm text-slate-400">Chargement…</div>;
  if (!user) return <Login />;
  return <Layout />;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <Shell />
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
