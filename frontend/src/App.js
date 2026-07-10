import "./App.css";
import Dashboard from "./components/Dashboard";
import { Toaster } from "sonner";

function App() {
  return (
    <div className="App">
      <Dashboard />
      <Toaster position="top-right" theme="light" />
    </div>
  );
}

export default App;
