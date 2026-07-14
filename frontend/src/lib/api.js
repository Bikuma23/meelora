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

  listEmployees: (params) => client.get("/employees", { params: params || {} }).then((r) => r.data),
  createEmployee: (d) => client.post("/employees", d).then((r) => r.data),
  updateEmployee: (id, d) => client.put(`/employees/${id}`, d).then((r) => r.data),
  deleteEmployee: (id) => client.delete(`/employees/${id}`).then((r) => r.data),
  importEmployees: (file) => { const fd = new FormData(); fd.append("file", file); return client.post("/employees/import", fd).then((r) => r.data); },
  importDepartments: (file) => { const fd = new FormData(); fd.append("file", file); return client.post("/departments/import", fd).then((r) => r.data); },
  downloadTemplate: (kind) => client.get(`/${kind}/template`, { responseType: "blob" }).then((r) => r.data),

  budgetPreview: (id, override, params) => client.post(`/employees/${id}/budget-preview`, { override }, { params }).then((r) => r.data),
  saveBudgetOverride: (id, override, params) => client.put(`/employees/${id}/budget-override`, { override }, { params }).then((r) => r.data),
  applyAugmentation: (body, params) => client.post("/budget/apply-augmentation", body, { params }).then((r) => r.data),

  getHypotheses: (year) => client.get("/hypotheses", { params: year ? { year } : {} }).then((r) => r.data),
  updateHypotheses: (d, year) => client.put("/hypotheses", d, { params: year ? { year } : {} }).then((r) => r.data),
  getBudget: (params) => client.get("/budget", { params }).then((r) => r.data),
  getBudgetCompare: (params) => client.get("/budget/compare", { params }).then((r) => r.data),
  getBudgetEvolution: (params) => client.get("/budget/evolution", { params }).then((r) => r.data),

  listYears: () => client.get("/years").then((r) => r.data),
  createYear: (d) => client.post("/years", d).then((r) => r.data),
  setActiveYear: (year) => client.put("/years/active", { year }).then((r) => r.data),

  downloadEmployeeFiche: (eid, year, scenario) => client.get(`/employees/${eid}/fiche-pdf`, { params: { ...(year ? { year } : {}), ...(scenario ? { scenario } : {}) }, responseType: "blob" }).then((r) => r.data),

  getLocks: (params) => client.get("/budget/locks", { params }).then((r) => r.data),
  setLock: (d) => client.post("/budget/lock", d).then((r) => r.data),
  getBudgetNoEntry: (params) => client.get("/budget/no-entry", { params }).then((r) => r.data),
  inactivateNoEntry: (params) => client.post("/budget/inactivate-no-entry", {}, { params }).then((r) => r.data),

  listUsers: () => client.get("/users").then((r) => r.data),
  createUser: (d) => client.post("/users", d).then((r) => r.data),
  updateUser: (id, d) => client.put(`/users/${id}`, d).then((r) => r.data),
  deleteUser: (id) => client.delete(`/users/${id}`).then((r) => r.data),

  listDepartments: () => client.get("/departments").then((r) => r.data),
  createDepartment: (d) => client.post("/departments", d).then((r) => r.data),
  updateDepartment: (id, d) => client.put(`/departments/${id}`, d).then((r) => r.data),
  deleteDepartment: (id) => client.delete(`/departments/${id}`).then((r) => r.data),

  getJournal: () => client.get("/journal").then((r) => r.data),
  downloadReport: (kind, department, year, scenario) => client.get(`/reports/${kind}`, {
    params: { ...(department && department !== "all" ? { department } : {}), ...(year ? { year } : {}), ...(scenario ? { scenario } : {}) }, responseType: "blob",
  }).then((r) => r.data),
  getPnl: (params) => client.get("/reports/pnl", { params }).then((r) => r.data),
  getByClass: (params) => client.get("/reports/by-class", { params }).then((r) => r.data),
  getScenarioCompare: (params) => client.get("/reports/scenario-compare", { params }).then((r) => r.data),
  getCustomColumns: () => client.get("/reports/custom-columns").then((r) => r.data),
  getCustomReport: (params) => client.get("/reports/custom", { params }).then((r) => r.data),
  getPreferences: () => client.get("/me/preferences").then((r) => r.data),
  updatePreferences: (body) => client.put("/me/preferences", body).then((r) => r.data),
  listReportTemplates: () => client.get("/report-templates").then((r) => r.data),
  createReportTemplate: (body) => client.post("/report-templates", body).then((r) => r.data),
  deleteReportTemplate: (id) => client.delete(`/report-templates/${id}`).then((r) => r.data),
  downloadReportParams: (kind, params) => client.get(`/reports/${kind}`, { params, responseType: "blob" }).then((r) => r.data),

  acctDashboard: () => client.get("/acct/dashboard").then((r) => r.data),
  acctGetTemplate: () => client.get("/acct/template").then((r) => r.data),
  acctUploadTemplate: (file) => { const fd = new FormData(); fd.append("file", file); return client.post("/acct/template", fd).then((r) => r.data); },
  acctUploadBV: (file, params) => { const fd = new FormData(); fd.append("file", file); return client.post("/acct/bv", fd, { params }).then((r) => r.data); },
  acctPeriods: () => client.get("/acct/periods").then((r) => r.data),
  acctLock: (params) => client.post("/acct/period/lock", {}, { params }).then((r) => r.data),
  acctReport: (params) => client.get("/acct/report", { params }).then((r) => r.data),
  acctReportExcel: (params) => client.get("/acct/report/excel", { params, responseType: "blob" }).then((r) => r.data),
  acctAccounts: () => client.get("/acct/accounts").then((r) => r.data),
  acctAccountMap: (assignments, params) => client.post("/acct/account-map", { assignments }, { params }).then((r) => r.data),
  acctSummary: (params) => client.get("/acct/summary", { params }).then((r) => r.data),
};
