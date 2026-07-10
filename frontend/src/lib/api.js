import axios from "axios";

const client = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

client.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export const api = {
  login: (email, password) => client.post("/auth/login", { email, password }).then((r) => r.data),
  logout: () => client.post("/auth/logout").then((r) => r.data),
  me: () => client.get("/auth/me").then((r) => r.data),

  listEmployees: (q) => client.get("/employees", { params: q ? { q } : {} }).then((r) => r.data),
  createEmployee: (d) => client.post("/employees", d).then((r) => r.data),
  updateEmployee: (id, d) => client.put(`/employees/${id}`, d).then((r) => r.data),
  deleteEmployee: (id) => client.delete(`/employees/${id}`).then((r) => r.data),
  importEmployees: (file) => { const fd = new FormData(); fd.append("file", file); return client.post("/employees/import", fd).then((r) => r.data); },
  importDepartments: (file) => { const fd = new FormData(); fd.append("file", file); return client.post("/departments/import", fd).then((r) => r.data); },
  downloadTemplate: (kind) => client.get(`/${kind}/template`, { responseType: "blob" }).then((r) => r.data),

  budgetPreview: (id, override) => client.post(`/employees/${id}/budget-preview`, { override }).then((r) => r.data),
  saveBudgetOverride: (id, override) => client.put(`/employees/${id}/budget-override`, { override }).then((r) => r.data),

  getHypotheses: () => client.get("/hypotheses").then((r) => r.data),
  updateHypotheses: (d) => client.put("/hypotheses", d).then((r) => r.data),
  getBudget: (params) => client.get("/budget", { params }).then((r) => r.data),

  listDepartments: () => client.get("/departments").then((r) => r.data),
  createDepartment: (d) => client.post("/departments", d).then((r) => r.data),
  updateDepartment: (id, d) => client.put(`/departments/${id}`, d).then((r) => r.data),
  deleteDepartment: (id) => client.delete(`/departments/${id}`).then((r) => r.data),

  getJournal: () => client.get("/journal").then((r) => r.data),
  downloadReport: (kind, department) => client.get(`/reports/${kind}`, {
    params: department && department !== "all" ? { department } : {}, responseType: "blob",
  }).then((r) => r.data),
};
